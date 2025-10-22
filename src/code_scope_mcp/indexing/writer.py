import sqlite3
import re
import inspect
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from .models import Symbol
from .languages import LanguageDefinition
from .timing_utils import profile_db_operation
from .exceptions import DuplicateRelationshipException, DuplicateSymbolException


class IndexWriter:
    """
    Abstracts all database write operations, providing a clean API for analyzers.
    This version performs atomic database operations without batching.
    """
    QNAME_VALIDATION_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\[\]]+(:|\.|:__FILE__)[a-zA-Z0-9_\-\[\]]*$")

    def __init__(self, db_connection: sqlite3.Connection, logger):
        self.db_connection = db_connection
        self.logger = logger
        self.language_definition: Optional[LanguageDefinition] = None
        self.symbol_type_ids: Dict[str, int] = {}
        self.relationship_type_ids: Dict[str, int] = {}
        self._file_id_cache: Dict[str, int] = {}

        # Batching support
        self._relationship_batch_mode = False
        self._relationship_batch: List[Tuple[int, int, int, float]] = []

        self._load_type_ids()

    def reset_batch_state(self):
        """Reset batch relationship state to ensure clean operation."""
        self._relationship_batch_mode = False
        self._relationship_batch = []
        self.logger.log("IndexWriter", "Batch state reset")

    def set_language_definition(self, language_definition: LanguageDefinition):
        """Sets the language definition for the writer."""
        self.language_definition = language_definition

    def _load_type_ids(self):
        """On initialization, query and cache all IDs from lookup tables."""
        cursor = self.db_connection.cursor()
        try:
            cursor.execute("SELECT id, name FROM symbol_types")
            for row in cursor.fetchall():
                self.symbol_type_ids[row["name"]] = row["id"]

            cursor.execute("SELECT id, name FROM relationship_types")
            for row in cursor.fetchall():
                self.relationship_type_ids[row["name"]] = row["id"]
        finally:
            cursor.close()

    def _validate_qname(self, qname: str, context: str):
        # Allow file qnames, which don't have a separator
        if ":" not in qname and "." not in qname:
            return

        if not self.QNAME_VALIDATION_REGEX.match(qname):
            raise ValueError(f"IndexWriter: Invalid qname format in {context}: '{qname}'")

    def _extract_caller_location(self) -> Optional[str]:
        """
        Extract the caller's file name and line number from the call stack.

        Returns:
            A string in format "filename.ext:line_no" or None if extraction fails.
        """
        try:
            # Get the call stack, skip this method (index 0) and the calling method (index 1)
            # to get the actual caller
            frame = inspect.stack()[2]  # Index 2 gets the caller of add_unresolved_relationship
            if "timing_utils" in frame.filename:
                frame = inspect.stack()[3]

            # Extract filename (basename only, no full path)
            filename = Path(frame.filename).name

            # Extract line number
            line_no = frame.lineno

            # Format as "filename.ext:line_no"
            return f"{filename}:{line_no}"

        except (IndexError, AttributeError, OSError) as e:
            # Log the error but don't fail - return None for graceful degradation
            self.logger.log("IndexWriter", f"Warning: Failed to extract caller location: {e}")
            return None

    def _get_or_create_file_id(self, file_path: str, language: str) -> int:
        """Gets the file ID from the cache or database, creating it if it doesn't exist."""
        if file_path in self._file_id_cache:
            return self._file_id_cache[file_path]

        cursor = self.db_connection.cursor()
        try:
            cursor.execute("SELECT id FROM files WHERE path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                file_id = row["id"]
                self._file_id_cache[file_path] = file_id
                return file_id
            else:
                p = Path(file_path)
                size = p.stat().st_size if p.exists() else 0
                cursor.execute(
                    "INSERT OR IGNORE INTO files (path, size, language) VALUES (?, ?, ?)",
                    (file_path, size, language),
                )
                # In case of a race condition with another process, re-fetch the ID
                cursor.execute("SELECT id FROM files WHERE path = ?", (file_path,))
                row = cursor.fetchone()
                if not row:
                    # This should not happen in a single-threaded writer context
                    raise RuntimeError(f"Failed to create or find file_id for {file_path}")

                file_id = row["id"]
                self.db_connection.commit()
                self._file_id_cache[file_path] = file_id
                return file_id
        finally:
            cursor.close()

    @profile_db_operation()
    def add_file_symbol(self, symbol: Symbol):
        """Adds a file symbol to the database, creating the file entry if needed.

        Returns the symbol object with the symbol.id and symbol.file_id populated.
        """
        if symbol.symbol_type != "file":
            raise ValueError(f"add_file_symbol called with non-file symbol type '{symbol.symbol_type}'")

        self._validate_qname(symbol.qname, f"add_file_symbol for {symbol.name}")
        if self.language_definition and symbol.symbol_type not in self.language_definition.supported_symbol_types:
            raise ValueError(f"Unsupported symbol type '{symbol.symbol_type}' for language '{self.language_definition.language_name}'. Symbol: {symbol.name} ({symbol.qname}) in {symbol.file_path}")

        file_id = self._get_or_create_file_id(symbol.file_path, symbol.language)

        cursor = self.db_connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO code_symbols (file_id, name, qname, type_id, line_start) VALUES (?, ?, ?, ?, ?)",
                (file_id, symbol.name, symbol.qname, self.symbol_type_ids["file"], symbol.line_number),
            )
            symbol.id = cursor.lastrowid
            symbol.file_id = file_id
            self.db_connection.commit()

            self.logger.log("IndexWriter", f"add_symbol({symbol.qname})")

            return symbol
        finally:
            cursor.close()

    @profile_db_operation()
    def add_symbol(self, symbol: Symbol):
        """Adds a symbol directly to the database.

        For non-file symbols, symbol.file_id must be provided.
        Returns the symbol object with the symbol.id populated.
        """
        self._validate_qname(symbol.qname, f"add_symbol for {symbol.name}")
        if self.language_definition and symbol.symbol_type not in self.language_definition.supported_symbol_types:
            raise ValueError(f"Unsupported symbol type '{symbol.symbol_type}' for language '{self.language_definition.language_name}'. Symbol: {symbol.name} ({symbol.qname}) in {symbol.file_path}")

        if not symbol.symbol_type:
            raise ValueError(f"Symbol has no type: {symbol.name} ({symbol.qname}) in {symbol.file_path}")

        if symbol.symbol_type == "file":
            raise ValueError(f"Use add_file_symbol for file symbols, not add_symbol")

        if symbol.file_id is None:
            raise ValueError(f"Symbol file_id must be provided for non-file symbols: {symbol.name} ({symbol.qname})")

        type_id = self.symbol_type_ids.get(symbol.symbol_type)
        if type_id is None:
            raise ValueError(f"Unknown symbol type '{symbol.symbol_type}' for symbol: {symbol.name} ({symbol.qname})")

        cursor = self.db_connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO code_symbols (file_id, name, qname, type_id, line_start) VALUES (?, ?, ?, ?, ?)",
                (symbol.file_id, symbol.name, symbol.qname, type_id, symbol.line_number),
            )
            symbol.id = cursor.lastrowid
            self.db_connection.commit()
            self.logger.log("IndexWriter", f"add_symbol({symbol.qname})")
            return symbol
        except sqlite3.IntegrityError as e1:
            self.logger.mustLog("IndexWriter", f"Violates unique constraint: File: {symbol.file_path}, qname: {symbol.qname}, Line Nr: {symbol.line_number}")

            # Raise custom exception with attempted symbol details
            attempted_symbol = {
                'name': symbol.name,
                'symbol_type': symbol.symbol_type,
                'line_number': symbol.line_number
            }

            raise DuplicateSymbolException(
                file_id=symbol.file_id,
                qname=symbol.qname,
                attempted_symbol=attempted_symbol,
                file_path=symbol.file_path
            )
        finally:
            cursor.close()

    @contextmanager
    def batch_relationships(self):
        """Context manager for batching relationship operations.

        Usage:
            with writer.batch_relationships() as batch_writer:
                batch_writer.add_relationship(...)
                batch_writer.add_relationship(...)
                # All relationships executed as single batch operation

        Note: Nested batch contexts are not allowed.
        """
        if self._relationship_batch_mode:
            raise RuntimeError("Cannot nest batch_relationships() contexts")

        # Enter batch mode
        self._relationship_batch_mode = True
        self._relationship_batch = []

        try:
            yield self
        finally:
            # Execute batch and exit batch mode
            try:
                if self._relationship_batch:
                    self._execute_relationship_batch()
                self.logger.log("IndexWriter", f"Executed batch of {len(self._relationship_batch) if self._relationship_batch else 0} relationships")
            except Exception as e:
                # For production resilience, log the error and fall back to individual inserts if batch fails
                self.logger.log("IndexWriter", f"Batch execution failed, falling back to individual inserts: {e}")
                if self._relationship_batch:
                    self._execute_relationship_batch_fallback()
            finally:
                # Always reset state regardless of success/failure
                self._relationship_batch_mode = False
                self._relationship_batch = []

    def _execute_relationship_batch(self):
        """Execute all batched relationship operations in a single transaction."""
        if not self._relationship_batch:
            return

        cursor = self.db_connection.cursor()
        try:
            cursor.executemany(
                "INSERT INTO relationships (source_symbol_id, target_symbol_id, type_id, confidence) VALUES (?, ?, ?, ?)",
                self._relationship_batch
            )
        except sqlite3.IntegrityError as e1:
            for rel in self._relationship_batch:
                try:
                    cursor.execute(
                        "INSERT INTO relationships (source_symbol_id, target_symbol_id, type_id, confidence) VALUES (?, ?, ?, ?)",
                        rel
                    )
                except sqlite3.IntegrityError as e2:
                    # Log detailed information about the duplicate
                    source_id, target_id, type_id, confidence = rel
                    self.logger.mustLog("IndexWriter", f"DUPLICATE RELATIONSHIP: source_id={source_id}, target_id={target_id}, type_id={type_id}, error={e2}")

                    # Try to find existing relationship details
                    cursor.execute("""
                        SELECT rt.name as rel_type, s1.qname as source_qname, s2.qname as target_qname
                        FROM relationships r
                        JOIN relationship_types rt ON r.type_id = rt.id
                        JOIN code_symbols s1 ON r.source_symbol_id = s1.id
                        JOIN code_symbols s2 ON r.target_symbol_id = s2.id
                        WHERE r.source_symbol_id = ? AND r.target_symbol_id = ? AND r.type_id = ?
                    """, (source_id, target_id, type_id))

                    existing = cursor.fetchone()
                    existing_rel_details = None
                    if existing:
                        rel_type, source_qname, target_qname = existing
                        existing_rel_details = (rel_type, source_qname, target_qname)
                        self.logger.mustLog("IndexWriter", f"EXISTING RELATIONSHIP: {source_qname} --({rel_type})--> {target_qname}")

                    # Raise custom exception with details
                    raise DuplicateRelationshipException(
                        source_id=source_id,
                        target_id=target_id,
                        type_id=type_id,
                        existing_rel_details=existing_rel_details
                    )

            self.db_connection.commit()
            self.logger.log("IndexWriter", f"Executed batch of {len(self._relationship_batch)} relationships")
        finally:
            cursor.close()
            self._relationship_batch = []

    def _execute_relationship_batch_fallback(self):
        """Execute batched relationship operations individually when batch execution fails."""
        if not self._relationship_batch:
            return

        cursor = self.db_connection.cursor()
        successful_inserts = 0
        try:
            for rel in self._relationship_batch:
                try:
                    cursor.execute(
                        "INSERT INTO relationships (source_symbol_id, target_symbol_id, type_id, confidence) VALUES (?, ?, ?, ?)",
                        rel
                    )
                    successful_inserts += 1
                except sqlite3.IntegrityError as e:
                    # Log the duplicate but continue with others
                    source_id, target_id, type_id, confidence = rel
                    self.logger.log("IndexWriter", f"Skipped duplicate relationship in fallback: source_id={source_id}, target_id={target_id}, type_id={type_id}")

            if successful_inserts > 0:
                self.db_connection.commit()
                self.logger.log("IndexWriter", f"Fallback inserted {successful_inserts} individual relationships")
        finally:
            cursor.close()
            self._relationship_batch = []

    @profile_db_operation()
    def add_relationship(
        self,
        source_symbol_id: int,
        target_symbol_id: int,
        rel_type: str,
        source_qname: str,
        target_qname: str,
        confidence: float = 1.0,
    ):
        """Adds a resolved relationship to the database.

        If in batch mode, collects the relationship for later batch execution.
        Otherwise, executes immediately.
        """
        self._validate_qname(source_qname, "add_relationship source")
        self._validate_qname(target_qname, "add_relationship target")
        if self.language_definition and rel_type not in self.language_definition.supported_relationship_types:
            raise ValueError(f"Relationship type not found '{rel_type}' for language '{self.language_definition.language_name}'. Relationship from {source_qname} to {target_qname}.")

        rel_type_id = self.relationship_type_ids.get(rel_type)
        if rel_type_id is None:
            self.logger.log("IndexWriter", f"Unknown relationship type '{rel_type}' when adding relationship.")
            return

        if self._relationship_batch_mode:
            # Collect for batch execution
            self._relationship_batch.append((source_symbol_id, target_symbol_id, rel_type_id, confidence))
            self.logger.log("IndexWriter", f"Batched relationship: {source_qname} {rel_type} {target_qname}")
        else:
            # Execute immediately
            cursor = self.db_connection.cursor()
            try:
                cursor.execute(
                    "INSERT INTO relationships (source_symbol_id, target_symbol_id, type_id, confidence) VALUES (?, ?, ?, ?)",
                    (source_symbol_id, target_symbol_id, rel_type_id, confidence),
                )
                self.db_connection.commit()
                self.logger.log(
                    "IndexWriter",
                    f"add_relationship({source_qname} {rel_type} {target_qname})"
                )
            finally:
                cursor.close()

    @profile_db_operation()
    def add_unresolved_relationship(
        self, source_symbol_id: int, source_qname: str, target_name: str, rel_type: str, needs_type: str, target_qname: str = None, intermediate_symbol_qname: str = None, target_resolver_name: str = None
    ):
        """Adds an unresolved relationship directly to the database.

            Automatically captures the caller's file name and line number for debugging purposes.

            Args:
            source_symbol_id      The ID of the symbol which forms the left hand side of the unresolved relationship
            source_qname          The qname of the symbol which forms the left hand side of the unresolved relationship
            target_name           The plain name of the symbol which is on the right hand side of the relationship. Used by relationship handlers when a target_qname is not available/able to be computed yet.
            rel_type              The type of relationship to be created.
            needs_type            The type of relationship which must already exist in the database. This is a hint to aid in correct order of resolution.
            target_qname          Optional. The qname of the symbol which forms the right hand side of the unresolved relationship.
            intermediate_symbol_qname   Optional. A hint which may help in resolving an indirect relationship.
            target_resolver_name  Optional. Name of the resolver class expected to handle this unresolved relationship.

        """
        self._validate_qname(source_qname, "add_unresolved_relationship source")
        if target_qname:
            self._validate_qname(target_qname, "add_unresolved_relationship target")

        if self.language_definition and rel_type not in self.language_definition.supported_relationship_types:
            raise ValueError(f"Relationship type not found '{rel_type}' for language '{self.language_definition.language_name}'. Unresolved relationship from ID {source_symbol_id} {source_qname} to {target_name}.")

        rel_type_id = self.relationship_type_ids.get(rel_type)
        needs_type_id = self.relationship_type_ids.get(needs_type)

        if not rel_type_id or not needs_type_id:
            raise ValueError(f"Skipping unresolved relationship due to unknown type: rel_type='{rel_type}', needs_type='{needs_type}'")

        # Automatically extract caller location information
        creator_location = self._extract_caller_location()

        cursor = self.db_connection.cursor()

        cursor.execute(
            """
            INSERT INTO unresolved_relationships
            (source_symbol_id, relationship_type_id, target_name, target_qname, needs_type_id, intermediate_symbol_qname, creator_location, target_resolver_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_symbol_id,
                rel_type_id,
                target_name,
                target_qname,
                needs_type_id,
                intermediate_symbol_qname,
                creator_location,
                target_resolver_name,
            ),
        )
        self.db_connection.commit()
        if intermediate_symbol_qname:
            self.logger.log("IndexWriter", f"add_unresolved_relationship({rel_type} from ID {source_symbol_id} {source_qname} to {target_name} (needs: {needs_type}) via {intermediate_symbol_qname})")
        else:
            self.logger.log("IndexWriter", f"add_unresolved_relationship({rel_type} from ID {source_symbol_id} {source_qname} to {target_name} (needs: {needs_type})")


    def delete_unresolved_relationship(self, resolved_id: int):
        """Deletes a single resolved relationship from the unresolved_relationships table."""
        cursor = self.db_connection.cursor()
        try:
            query = "DELETE FROM unresolved_relationships WHERE id = ?"
            cursor.execute(query, (resolved_id,))
            self.db_connection.commit()
        finally:
            cursor.close()

    def delete_unresolved_relationships(self, resolved_ids: List[int]):
        """Deletes resolved relationships from the unresolved_relationships table."""
        if not resolved_ids:
            return

        cursor = self.db_connection.cursor()
        try:
            placeholders = ",".join("?" for _ in resolved_ids)
            query = f"DELETE FROM unresolved_relationships WHERE id IN ({placeholders})"
            cursor.execute(query, resolved_ids)
            self.db_connection.commit()
        finally:
            cursor.close()

    @profile_db_operation()
    def remove_file_from_index(self, file_path: str):
        """
        Remove a file and all associated data from the index.

        Uses SQLite CASCADE DELETE to automatically clean up:
        - All symbols for the file
        - All relationships involving those symbols
        - All unresolved relationships for those symbols
        - All symbol properties for those symbols
        """
        cursor = self.db_connection.cursor()
        try:
            # Debug: Check if file exists before deletion
            cursor.execute("SELECT id FROM files WHERE path = ?", (file_path,))
            file_row = cursor.fetchone()

            if file_row:
                file_id = file_row["id"]
                print(f"DEBUG: Removing file from index: {file_path} (ID: {file_id})")

                # Single DELETE triggers full cascade cleanup via foreign key constraints
                cursor.execute("DELETE FROM files WHERE path = ?", (file_path,))
                self.db_connection.commit()

                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    self.logger.log("IndexWriter", f"Removed file from index (CASCADE): {file_path}")
                    print(f"DEBUG: Successfully removed file from index: {file_path}")
                else:
                    self.logger.log("IndexWriter", f"File not found in index: {file_path}")
                    print(f"DEBUG: File not found in index: {file_path}")

                return deleted_count > 0
            else:
                print(f"DEBUG: File not found in database: {file_path}")
                return False

        finally:
            cursor.close()


class IndexUpserter(IndexWriter):
    """Modified writer that UPSERTs instead of plain INSERTs."""

    def __init__(self, *args, session_timestamp=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_timestamp = session_timestamp or datetime.now()

    @profile_db_operation()
    def add_file_symbol(self, symbol: Symbol):
        """UPSERT file symbols: Insert if new, update timestamp if existing."""
        if symbol.symbol_type != "file":
            raise ValueError(f"add_file_symbol called with non-file symbol type '{symbol.symbol_type}'")

        self._validate_qname(symbol.qname, f"add_file_symbol for {symbol.name}")
        if self.language_definition and symbol.symbol_type not in self.language_definition.supported_symbol_types:
            raise ValueError(f"Unsupported symbol type '{symbol.symbol_type}' for language '{self.language_definition.language_name}'. Symbol: {symbol.name} ({symbol.qname}) in {symbol.file_path}")

        file_id = self._get_or_create_file_id(symbol.file_path, symbol.language)

        cursor = self.db_connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO code_symbols
                    (file_id, name, qname, type_id, line_start, last_touched)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id, qname) DO UPDATE SET
                    line_start = excluded.line_start,
                    last_touched = excluded.last_touched
            """, (file_id, symbol.name, symbol.qname, self.symbol_type_ids["file"], symbol.line_number, self.session_timestamp))

            # Get the ID of existing or newly inserted record
            cursor.execute("SELECT id FROM code_symbols WHERE file_id = ? AND qname = ?", (file_id, symbol.qname))
            row = cursor.fetchone()
            if row:
                symbol.id = row["id"]
            symbol.file_id = file_id
            self.db_connection.commit()

            self.logger.log("IndexUpserter", f"add_file_symbol(UPSERT {symbol.qname})")
            return symbol
        finally:
            cursor.close()

    @profile_db_operation()
    def add_symbol(self, symbol: Symbol):
        """UPSERT: Insert if new, update timestamp if existing."""
        # Always call validate_qname
        self._validate_qname(symbol.qname, f"add_symbol for {symbol.name}")
        if self.language_definition and symbol.symbol_type not in self.language_definition.supported_symbol_types:
            raise ValueError(f"Unsupported symbol type '{symbol.symbol_type}' for language '{self.language_definition.language_name}'. Symbol: {symbol.name} ({symbol.qname}) in {symbol.file_path}")

        if not symbol.symbol_type:
            raise ValueError(f"Symbol has no type: {symbol.name} ({symbol.qname}) in {symbol.file_path}")

        if symbol.symbol_type == "file":
            raise ValueError("Use add_file_symbol for file symbols, not add_symbol")

        if symbol.file_id is None:
            raise ValueError(f"Symbol file_id must be provided for non-file symbols: {symbol.name} ({symbol.qname})")

        type_id = self.symbol_type_ids.get(symbol.symbol_type)
        if type_id is None:
            raise ValueError(f"Unknown symbol type '{symbol.symbol_type}' for symbol: {symbol.name} ({symbol.qname})")

        cursor = self.db_connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO code_symbols
                    (file_id, name, qname, type_id, line_start, last_touched)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id, qname) DO UPDATE SET
                    line_start = excluded.line_start,
                    last_touched = excluded.last_touched
            """, (symbol.file_id, symbol.name, symbol.qname, type_id, symbol.line_number, self.session_timestamp))
            # For UPSERT, get the ID of existing or newly inserted record
            cursor.execute("SELECT id FROM code_symbols WHERE file_id = ? AND qname = ?", (symbol.file_id, symbol.qname))
            row = cursor.fetchone()
            if row:
                symbol.id = row["id"]
            self.db_connection.commit()
            self.logger.log("IndexUpserter", f"add_symbol(UPSERT {symbol.qname})")
            return symbol
        finally:
            cursor.close()

    @profile_db_operation()
    def add_relationship(self, source_symbol_id: int, target_symbol_id: int, rel_type: str, source_qname: str, target_qname: str, confidence: float = 1.0):
        """UPSERT relationships."""
        self._validate_qname(source_qname, "add_relationship source")
        self._validate_qname(target_qname, "add_relationship target")
        if self.language_definition and rel_type not in self.language_definition.supported_relationship_types:
            raise ValueError(f"Relationship type not found '{rel_type}' for language '{self.language_definition.language_name}'. Relationship from {source_qname} to {target_qname}.")

        rel_type_id = self.relationship_type_ids.get(rel_type)
        if rel_type_id is None:
            self.logger.log("IndexUpserter", f"Unknown relationship type '{rel_type}' when adding relationship.")
            return

        # For UPSERT on relationships, use unique constraint on source, target, type
        cursor = self.db_connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO relationships
                    (source_symbol_id, target_symbol_id, type_id, confidence, last_touched)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_symbol_id, target_symbol_id, type_id) DO UPDATE SET
                    confidence = MAX(excluded.confidence, confidence),
                    last_touched = excluded.last_touched
            """, (source_symbol_id, target_symbol_id, rel_type_id, confidence, self.session_timestamp))
            self.db_connection.commit()
            self.logger.log("IndexUpserter", f"add_relationship(UPSERT {source_qname} {rel_type} {target_qname})")
        finally:
            cursor.close()

    def _execute_relationship_batch(self):
        """Override batch execution for UPSERT logic."""
        if not self._relationship_batch:
            return

        cursor = self.db_connection.cursor()
        try:
            for rel in self._relationship_batch:
                cursor.execute("""
                    INSERT INTO relationships
                        (source_symbol_id, target_symbol_id, type_id, confidence, last_touched)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source_symbol_id, target_symbol_id, type_id) DO UPDATE SET
                        confidence = MAX(excluded.confidence, confidence),
                        last_touched = excluded.last_touched
                """, rel + (self.session_timestamp,))
            self.db_connection.commit()
            self.logger.log("IndexUpserter", f"Executed batch UPSERT of {len(self._relationship_batch)} relationships")
        finally:
            cursor.close()
            self._relationship_batch = []

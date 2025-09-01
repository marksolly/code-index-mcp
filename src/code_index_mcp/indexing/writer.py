import sqlite3
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import Symbol
from .languages import LanguageDefinition
from .timing_utils import profile_db_operation


class IndexWriter:
    """
    Abstracts all database write operations, providing a clean API for analyzers.
    This version performs atomic database operations without batching.
    """
    QNAME_VALIDATION_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\/]+(:|\.|:__FILE__)[a-zA-Z0-9_\-]*$")

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
            if self._relationship_batch:
                self._execute_relationship_batch()
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
            self.db_connection.commit()
            self.logger.log("IndexWriter", f"Executed batch of {len(self._relationship_batch)} relationships")
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
            raise ValueError(f"Unsupported relationship type '{rel_type}' for language '{self.language_definition.language_name}'. Relationship from {source_qname} to {target_qname}.")

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
        self, source_symbol_id: int, source_qname: str, target_name: str, rel_type: str, needs_type: str, target_qname: str = None, intermediate_symbol_qname: str = None
    ):
        """Adds an unresolved relationship directly to the database.

            Args:
            source_symbol_id    The ID of the symbol which forms the left hand side of the unresolved relationship
            source_qname        The qname of the symbol which forms the left hand side of the unresolved relationship
            target_name         The plain name of the symbol which is on the right hand side of the relationship. Used by relationship handlers when a target_qname is not available/able to be computed yet.
            rel_type            The type of relationship to be created.
            needs_type          The type of relationship which must already exist in the database. This is a hint to aid in correct order of resolution.
            target_qname        Optional. The qname of the symbol which forms the right hand side of the unresolved relationship.
            intermediate_symbol_qname   Optional. A hint which may help in resolving an indirect relationship.

        """
        self._validate_qname(source_qname, "add_unresolved_relationship source")
        if target_qname:
            self._validate_qname(target_qname, "add_unresolved_relationship target")

        if self.language_definition and rel_type not in self.language_definition.supported_relationship_types:
            raise ValueError(f"Unsupported relationship type '{rel_type}' for language '{self.language_definition.language_name}'. Unresolved relationship from ID {source_symbol_id} {source_qname} to {target_name}.")

        rel_type_id = self.relationship_type_ids.get(rel_type)
        needs_type_id = self.relationship_type_ids.get(needs_type)

        if not rel_type_id or not needs_type_id:
            raise ValueError(f"Skipping unresolved relationship due to unknown type: rel_type='{rel_type}', needs_type='{needs_type}'")

        cursor = self.db_connection.cursor()

        cursor.execute(
            """
            INSERT INTO unresolved_relationships
            (source_symbol_id, relationship_type_id, target_name, target_qname, needs_type_id, intermediate_symbol_qname)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_symbol_id,
                rel_type_id,
                target_name,
                target_qname,
                needs_type_id,
                intermediate_symbol_qname,
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

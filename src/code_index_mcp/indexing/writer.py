import sqlite3
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Optional

from .models import Symbol
from .languages import LanguageDefinition


class IndexWriter:
    """
    Abstracts all database write operations, providing a clean API for analyzers
    and handling performance optimizations like batching.
    """
    QNAME_VALIDATION_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\/]+(:|\.)[a-zA-Z0-9_\-]+$")

    def __init__(self, db_connection: sqlite3.Connection, logger):
        self.db_connection = db_connection
        self.logger = logger
        self.language_definition: Optional[LanguageDefinition] = None # Initialize as None
        self.symbol_type_ids: Dict[str, int] = {}
        self.relationship_type_ids: Dict[str, int] = {}
        self._symbol_buffer: List[Symbol] = []
        self._relationship_buffer: List[Dict[str, Any]] = []
        self._unresolved_buffer: List[Dict[str, Any]] = []
        self._file_id_cache: Dict[str, int] = {}
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
            raise ValueError(f"IndexWriter: Invalid qname format in {context}: '{qname}'");

    def add_symbol(self, symbol: Symbol):
        """Adds a symbol to the in-memory buffer."""
        self._validate_qname(symbol.qname, f"add_symbol for {symbol.name}")
        if self.language_definition and symbol.symbol_type not in self.language_definition.supported_symbol_types:
            self.logger.log("IndexWriter", f"Unsupported symbol type '{symbol.symbol_type}' for language '{self.language_definition.language_name}'. Symbol: {symbol.name} ({symbol.qname}) in {symbol.file_path}")
            return # Skip adding unsupported symbol types
        self._symbol_buffer.append(symbol)

    def add_relationship(
        self,
        source_symbol_id: int,
        target_symbol_id: int,
        rel_type: str,
        source_qname: str,
        target_qname: str,
        confidence: float = 1.0,
    ):
        self._validate_qname(source_qname, "add_relationship source")
        self._validate_qname(target_qname, "add_relationship target")
        if self.language_definition and rel_type not in self.language_definition.supported_relationship_types:
            self.logger.log("IndexWriter", f"Unsupported relationship type '{rel_type}' for language '{self.language_definition.language_name}'. Relationship from {source_qname} to {target_qname}.")
            return # Skip adding unsupported relationship types
        """
        Adds a resolved relationship to the in-memory buffer.
        Designed for use in Phase 2/3, where symbol IDs are already known.
        """
        self._relationship_buffer.append(
            {
                "source_id": source_symbol_id,
                "target_id": target_symbol_id,
                "type": rel_type,
                "confidence": confidence,
                "source_qname": source_qname,
                "target_qname": target_qname,
            }
        )

    def add_unresolved_relationship(
        self, source_qname: str, target_name: str, rel_type: str, needs_type: str, target_qname: str = None, intermediate_symbol_qname: str = None
    ):
        self._validate_qname(source_qname, "add_unresolved_relationship source")
        if target_qname:
            self._validate_qname(target_qname, "add_unresolved_relationship target")

        if self.language_definition and rel_type not in self.language_definition.supported_relationship_types:
            self.logger.log("IndexWriter", f"Unsupported relationship type '{rel_type}' for language '{self.language_definition.language_name}'. Unresolved relationship from {source_qname} to {target_name}.")
            return # Skip adding unsupported relationship types
        """
        Adds an unresolved relationship to the in-memory buffer.
        Designed for use in Phase 1, where source symbol IDs are not yet known.
        """
        self._unresolved_buffer.append(
            {
                "source_qname": source_qname,
                "target_name": target_name,
                "target_qname": target_qname,
                "rel_type": rel_type,
                "needs_type": needs_type,
                "intermediate_symbol_qname": intermediate_symbol_qname,
            }
        )

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

    def flush(self):
        """
        Writes all buffered data to the database in efficient batches and commits.
        """
        if not self._symbol_buffer and not self._relationship_buffer and not self._unresolved_buffer:
            return

        cursor = self.db_connection.cursor()
        try:
            self._flush_files(cursor)
            self._flush_symbols(cursor)

            # Only resolve qnames if there are unresolved relationships to process
            if self._unresolved_buffer:
                qname_id_map = self._get_symbol_id_map()
                self._flush_unresolved_relationships(cursor, qname_id_map)

            self._flush_relationships(cursor)

            self.db_connection.commit()
        finally:
            cursor.close()
            # Clear buffers after a successful flush
            self._symbol_buffer.clear()
            self._relationship_buffer.clear()
            self._unresolved_buffer.clear()

    def _flush_files(self, cursor: sqlite3.Cursor):
        """Ensures all file paths from the symbol buffer exist in the files table."""
        file_info = {s.file_path: s.language for s in self._symbol_buffer}
        new_files = {fp for fp in file_info if fp not in self._file_id_cache}

        if not new_files:
            return

        file_data = []
        for path_str in new_files:
            p = Path(path_str)
            lang = file_info[path_str]
            file_data.append((path_str, p.stat().st_size if p.exists() else 0, lang))

        cursor.executemany("INSERT OR IGNORE INTO files (path, size, language) VALUES (?, ?, ?)", file_data)

        # Update cache for all files we might need
        placeholders = ",".join("?" for _ in new_files)
        cursor.execute(f"SELECT id, path FROM files WHERE path IN ({placeholders})", list(new_files))
        for row in cursor.fetchall():
            self._file_id_cache[row["path"]] = row["id"]

    def _flush_symbols(self, cursor: sqlite3.Cursor):
        """Flushes the symbol buffer to the code_symbols table."""
        if not self._symbol_buffer:
            return

        symbol_data = []
        for s in self._symbol_buffer:
            if not s.symbol_type:
                raise ValueError(f"Symbol has no type: {s.name} ({s.qname}) in {s.file_path}")
            
            type_id = self.symbol_type_ids.get(s.symbol_type)
            if type_id is None:
                raise ValueError(f"Unknown symbol type '{s.symbol_type}' for symbol: {s.name} ({s.qname})")

            symbol_data.append(
                (
                    self._file_id_cache.get(s.file_path),
                    s.name,
                    s.qname,
                    type_id,
                    s.line_number,
                )
            )

        cursor.executemany(
            "INSERT INTO code_symbols (file_id, name, qname, type_id, line_start) VALUES (?, ?, ?, ?, ?)",
            symbol_data,
        )

    def _get_symbol_id_map(self) -> Dict[str, List[int]]:
        """
        Creates a map of qname -> [symbol_id] for all source symbols in the
        unresolved buffer. Handles cases where a qname may not be unique.
        """
        qnames_needed: Set[str] = {rel["source_qname"] for rel in self._unresolved_buffer}
        if not qnames_needed:
            return {}

        qname_id_map: Dict[str, List[int]] = defaultdict(list)
        cursor = self.db_connection.cursor()
        try:
            placeholders = ",".join("?" for _ in qnames_needed)
            query = f"SELECT id, qname FROM code_symbols WHERE qname IN ({placeholders})"
            cursor.execute(query, list(qnames_needed))
            for row in cursor.fetchall():
                qname_id_map[row["qname"]].append(row["id"])
            return qname_id_map
        finally:
            cursor.close()

    def _flush_relationships(self, cursor: sqlite3.Cursor):
        """Flushes the relationship buffer to the relationships table."""
        if not self._relationship_buffer:
            return

        rel_data = []
        for rel in self._relationship_buffer:
            rel_type_name = rel["type"]
            rel_type_id = self.relationship_type_ids.get(rel_type_name)
            if rel_type_id is None:
                self.logger.log("IndexWriter", f"Unknown relationship type '{rel_type_name}' when flushing resolved relationships.")
                continue

            rel_data.append(
                (
                    rel["source_id"],
                    rel["target_id"],
                    rel_type_id,
                    rel["confidence"],
                )
            )
            self.logger.log(
                "IndexWriter",
                f"Saved relationship: {rel_type_name} from {rel['source_qname']} to {rel['target_qname']}",
            )

        if rel_data:
            cursor.executemany(
                "INSERT INTO relationships (source_symbol_id, target_symbol_id, type_id, confidence) VALUES (?, ?, ?, ?)",
                rel_data,
            )

    def _flush_unresolved_relationships(self, cursor: sqlite3.Cursor, qname_id_map: Dict[str, List[int]]):
        """Flushes the unresolved buffer to the unresolved_relationships table."""
        if not self._unresolved_buffer:
            return

        unresolved_data = []
        for rel in self._unresolved_buffer:
            rel_type_name = rel["rel_type"]
            needs_type_name = rel["needs_type"]

            rel_type_id = self.relationship_type_ids.get(rel_type_name)
            needs_type_id = self.relationship_type_ids.get(needs_type_name)

            if not rel_type_id or not needs_type_id:
                self.logger.log("IndexWriter", f"Skipping unresolved relationship due to unknown type: rel_type='{rel_type_name}', needs_type='{needs_type_name}'")
                continue

            source_ids = qname_id_map.get(rel["source_qname"], [])

            if not source_ids:
                self.logger.log("IndexWriter", f"Skipping unresolved relationship due to missing source symbol ID for qname: {rel['source_qname']}")
                continue

            # Create an unresolved entry for each possible source symbol ID
            for source_id in source_ids:
                intermediate_symbol_qname = rel.get("intermediate_symbol_qname")
                unresolved_data.append(
                    (
                        source_id,
                        rel_type_id,
                        rel["target_name"],
                        rel.get("target_qname"),
                        needs_type_id,
                        intermediate_symbol_qname,
                    )
                )
                if intermediate_symbol_qname:
                    self.logger.log("IndexWriter", f"Saved unresolved: {rel_type_name} from {rel['source_qname']} to {rel['target_name']} (needs: {needs_type_name}) via {intermediate_symbol_qname}")
                else:
                    self.logger.log("IndexWriter", f"Saved unresolved: {rel_type_name} from {rel['source_qname']} to {rel['target_name']} (needs: {needs_type_name})")

        if unresolved_data:
            cursor.executemany(
                """
                INSERT INTO unresolved_relationships
                (source_symbol_id, relationship_type_id, target_name, target_qname, needs_type_id, intermediate_symbol_qname)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                unresolved_data,
            )

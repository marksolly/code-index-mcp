import sqlite3
import re
from typing import Any, Dict, List, Optional

from .indexing_logger import IndexingLogger


class IndexReader:
    """
    Abstracts database read operations with generalized search interfaces.
    """

    # Filter allows for wildcard characters. Some method can use LIKE matches.
    QNAME_VALIDATION_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\/\*\%]+(:|\.|\*|\%)[a-zA-Z0-9_\-\*\%]+$")

    def __init__(self, db_connection: sqlite3.Connection, logger: IndexingLogger):
        self.db_connection = db_connection
        self.logger = logger

    def _validate_qname(self, qname: str, context: str):
        # Allow file qnames, which don't have a separator
        if ":" not in qname and "." not in qname:
            return

        if not self.QNAME_VALIDATION_REGEX.match(qname):
            raise ValueError(f"IndexReader: Invalid qname format in {context}: '{qname}'");

    def find_symbols(
        self, name: Optional[str] = None, qname: Optional[str] = None, match_type: str = "exact"
    ) -> List[sqlite3.Row]:
        """
        Finds symbols by name or qname with exact or LIKE matching.
        At least one of name or qname must be provided.

        Expect that this method will possibly return multiple rows for a single qname.
        qnames are not guaranteed to be globally unique and our indexing system embraces 
        ambiguity by design. See NEW_LANG_GUIDE.md.
        """
        if not name and not qname:
            raise ValueError("At least one of 'name' or 'qname' must be provided.")

        conditions = []
        params = []
        operator = "=" if match_type == "exact" else "LIKE"

        if name:
            conditions.append(f"cs.name {operator} ?")
            params.append(name)
        if qname:
            self._validate_qname(qname, "find_symbols")
            conditions.append(f"cs.qname {operator} ?")
            params.append(qname)

        query = f"""
            SELECT cs.*, f.path as file_path, st.name as symbol_type
            FROM code_symbols cs
            JOIN files f ON cs.file_id = f.id
            JOIN symbol_types st ON cs.type_id = st.id
            WHERE {' AND '.join(conditions)}
        """
        
        cursor = self.db_connection.cursor()
        try:
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Build a more readable string for logging
            log_conditions = []
            log_context = {}
            if name:
                log_conditions.append(f"name={name}")
                log_context["name"] = name
            if qname:
                log_conditions.append(f"qname={qname}")
                log_context["qname"] = qname
            
            self.logger.log(
                "IndexReader", 
                f"find_symbols({', '.join(log_conditions)}): {len(results)} matches", 
                **log_context
            )
            return results
        finally:
            cursor.close()

    def find_relationships(self, rel_type: Optional[str] = None, source_id: Optional[int] = None, target_id: Optional[int] = None, source_qname: Optional[str] = None, target_qname: Optional[str] = None) -> List[sqlite3.Row]:
        """
        Finds resolved relationships based on various criteria.
        """
        conditions = []
        params = []

        if rel_type:
            conditions.append("rt.name = ?")
            params.append(rel_type)
        if source_id:
            conditions.append("r.source_symbol_id = ?")
            params.append(source_id)
        if target_id:
            conditions.append("r.target_symbol_id = ?")
            params.append(target_id)
        if source_qname:
            self._validate_qname(source_qname, "find_relationships source")
            conditions.append("cs_source.qname = ?")
            params.append(source_qname)
        if target_qname:
            self._validate_qname(target_qname, "find_relationships target")
            conditions.append("cs_target.qname = ?")
            params.append(target_qname)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT
                r.*,
                rt.name as rel_type_name,
                cs_source.qname as source_qname,
                cs_target.qname as target_qname
            FROM relationships r
            JOIN relationship_types rt ON r.type_id = rt.id
            JOIN code_symbols cs_source ON r.source_symbol_id = cs_source.id
            JOIN code_symbols cs_target ON r.target_symbol_id = cs_target.id
            WHERE {where_clause}
        """

        cursor = self.db_connection.cursor()
        try:
            cursor.execute(query, params)
            results = cursor.fetchall()
            self.logger.log("IndexReader", f"find_relationships({rel_type=}, {source_id=}, {target_id=}, {source_qname=}, {target_qname=}): {len(results)} matches")
            return results
        finally:
            cursor.close()

    def get_symbol_by_id(self, symbol_id: int) -> Optional[sqlite3.Row]:
        """
        Retrieves a symbol by its ID.
        """
        cursor = self.db_connection.cursor()
        try:
            query = """
                SELECT cs.*, f.path as file_path, st.name as symbol_type
                FROM code_symbols cs
                JOIN files f ON cs.file_id = f.id
                JOIN symbol_types st ON cs.type_id = st.id
                WHERE cs.id = ?
            """
            cursor.execute(query, (symbol_id,))
            result = cursor.fetchone()
            self.logger.log("IndexReader", f"get_symbol_by_id({symbol_id=}): {'found' if result else 'not found'}")
            return result
        finally:
            cursor.close()

    def find_unresolved(self, relationship_type: Optional[str] = None, **criteria) -> List[sqlite3.Row]:
        """
        Finds unresolved relationships with flexible criteria. If relationship_type
        is provided, it filters by that type.

        Supports exact and LIKE matching by appending '__like' to a key, and also
        supports checking for non-null values by appending '__is_not_null'.

        Example:
            reader.find_unresolved("imports", target_name="MyClass")
            reader.find_unresolved("calls", target_qname__like="%.__init__")
            reader.find_unresolved(target_qname__is_not_null=True)
        """
        cursor = self.db_connection.cursor()
        try:
            conditions = []
            params: List[Any] = []

            if relationship_type:
                cursor.execute("SELECT id FROM relationship_types WHERE name = ?", (relationship_type,))
                rel_type_row = cursor.fetchone()
                if not rel_type_row:
                    self.logger.log("IndexReader", f"Relationship type '{relationship_type}' not found.")
                    return []
                rel_type_id = rel_type_row["id"]
                conditions.append("ur.relationship_type_id = ?")
                params.append(rel_type_id)

            for key, value in criteria.items():
                if key.endswith("__like"):
                    column, operator = key[:-6], "LIKE"
                    conditions.append(f"ur.{column} {operator} ?")
                    params.append(value)
                elif key.endswith("__is_not_null"):
                    column, operator = key[:-13], "IS NOT NULL"
                    if value:
                        conditions.append(f"ur.{column} {operator}")
                else:
                    column, operator = key, "="
                    conditions.append(f"ur.{column} {operator} ?")
                    params.append(value)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            query = f"""
                SELECT ur.*, f.path as source_file_path, cs.qname as source_qname,
                       needs_type.name as needs_type_name, rel_type.name as rel_type
                FROM unresolved_relationships ur
                JOIN code_symbols cs ON ur.source_symbol_id = cs.id
                JOIN files f ON cs.file_id = f.id
                JOIN relationship_types needs_type ON ur.needs_type_id = needs_type.id
                JOIN relationship_types rel_type ON ur.relationship_type_id = rel_type.id
                WHERE {where_clause}
            """

            cursor.execute(query, params)
            results = cursor.fetchall()

            criteria_str = ", ".join(f"{k}={v}" for k, v in criteria.items())
            log_msg = f"find_unresolved('{relationship_type or ''}', {criteria_str}) -> {len(results)} matches"
            self.logger.log("IndexReader", log_msg)
            return results
        finally:
            cursor.close()

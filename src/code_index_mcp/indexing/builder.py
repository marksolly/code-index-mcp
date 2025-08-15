"""
Main index builder that coordinates all indexing components.

This module provides the main IndexBuilder class that orchestrates the entire
indexing process, from file scanning to relationship analysis to final index assembly.
"""

import os
import json
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..services.database import DatabaseService
from .models import ClassInfo, FileInfo, FileAnalysisResult, ValidationResult, DebugOptions
from .scanner import ProjectScanner
from ..analyzers.manager import LanguageAnalyzerManager


class RelationshipTypeCache:
    """Caches relationship types to avoid repetitive queries."""

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        self._cache: Dict[str, int] = {}
        self._is_fresh = False # To check if cache has been populated at least once

    def _load_all_types(self):
        """Loads all relationship types from the database into the cache."""
        conn = self.db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, id FROM relationship_types")
        for row in cursor.fetchall():
            self._cache[row['name']] = row['id']
        self._is_fresh = True

    def get_type_id(self, type_name: str) -> Optional[int]:
        """
        Gets the ID for a given relationship type name.
        Loads from DB on first call or if cache is cleared.
        """
        if not self._is_fresh or not self._cache: # Initial load or after clear()
            self._load_all_types()

        if type_name in self._cache:
            return self._cache[type_name]

        # If not in cache after initial load, query DB directly for this specific type
        # This handles cases where a type might be added after initial cache population
        # or if it was missed for some reason (though _load_all_types should be comprehensive).
        conn = self.db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM relationship_types WHERE name = ?", (type_name,))
        row = cursor.fetchone()
        if row:
            self._cache[type_name] = row['id'] # Cache it for future lookups
            return row['id']
        return None # Type not found in DB

    def clear(self):
        """Invalidates the cache."""
        self._cache.clear()
        self._is_fresh = False

    def refresh_from_db(self):
        """Clears cache and reloads all types from the database."""
        self.clear()
        self._load_all_types()


class RelationshipResolver:
    """Resolves relationships between symbols after the first pass."""

    def __init__(self, db_service: DatabaseService, debug_options: Optional[DebugOptions] = None):
        self.db_service = db_service
        self.debug_options = debug_options or DebugOptions()

    def _debug_symbol(self, symbol_name: str, language: str, message: str):
        if (self.debug_options and
            self.debug_options.symbol_names and
            any(s in symbol_name for s in self.debug_options.symbol_names) and
            self.debug_options.language and
            self.debug_options.language == language):
            print(f"DEBUG: [{language}] {symbol_name} -> {message}")

    def resolve_relationships(self):
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # In the first pass, we can't always determine the fully qualified name (qname)
        # of a target symbol, especially for `calls`, `instantiates`, and `inherits`
        # relationships in dynamically typed languages. We store the simple name
        # (`target_name`) as seen in the source code. In this second pass, we
        # resolve it to a specific symbol using the now-complete symbol table,
        # scoped by the source symbol's language.
        cursor.execute("""
            SELECT ur.source_symbol_id, ur.target_name, ur.target_qname, f.language, rt.name as rel_type_name
            FROM unresolved_relationships ur
            JOIN code_symbols cs ON ur.source_symbol_id = cs.id
            JOIN files f ON cs.file_id = f.id
            JOIN relationship_types rt ON ur.relationship_type_id = rt.id
        """)
        unresolved = cursor.fetchall()

        for rel in unresolved:
            self._debug_symbol(rel['target_name'], rel['language'], f"Resolving relationship for '{rel['target_name']}'")
            target_symbols = self._find_symbol(cursor, rel['target_name'], rel['language'], rel['target_qname'], rel['source_symbol_id'])
            if not target_symbols:
                self._debug_symbol(rel['target_name'], rel['language'], "No target symbols found.")
                continue

            self._debug_symbol(rel['target_name'], rel['language'], f"Found {len(target_symbols)} target symbol(s).")
            confidence = 1.0 / len(target_symbols)
            for target_symbol in target_symbols:
                rel_type = rel['rel_type_name']
                if rel_type == 'calls':
                    # Determine relationship type based on target symbol type
                    cursor.execute("SELECT name FROM symbol_types WHERE id = ?", (target_symbol['type_id'],))
                    symbol_type_row = cursor.fetchone()
                    if symbol_type_row:
                        symbol_type = symbol_type_row['name']
                        if symbol_type == 'class':
                            rel_type = "instantiates"
                elif rel_type == 'references_variable':
                    pass

                self._create_relationship(cursor, rel['source_symbol_id'], target_symbol['id'], rel_type, confidence)
            
        # Clear the unresolved relationships table
        cursor.execute("DELETE FROM unresolved_relationships")
        conn.commit()

    def _find_symbol(self, cursor, symbol_name: str, language: str, qname: Optional[str] = None, source_symbol_id: Optional[int] = None) -> List[Dict]:
        self._debug_symbol(symbol_name, language, f"Finding symbol '{symbol_name}' (qname: {qname}) in {language}")
        # First, try to find by exact qualified name or simple name
        base_query = """
            SELECT cs.id, cs.type_id, cs.qname, cs.name FROM code_symbols cs
            JOIN files f ON cs.file_id = f.id
            WHERE f.language = ? AND {}
        """
        
        # Prioritize exact qname match if provided
        if qname:
            self._debug_symbol(symbol_name, language, f"Attempting exact qname match: {qname}")
            query = base_query.format("cs.qname = ?")
            params = (language, qname)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            if rows:
                self._debug_symbol(symbol_name, language, "Found with exact qname match.")
                return [{'id': row['id'], 'type_id': row['type_id'], 'qname': row['qname'], 'name': row['name']} for row in rows]

        # Then try qualified name LIKE match (e.g., for 'self.method' where qname is 'Class.method')
        if "." in symbol_name or "\\" in symbol_name or "::" in symbol_name:
            self._debug_symbol(symbol_name, language, "Attempting qualified name match.")
            # Check if this is a method call on a class property
            if source_symbol_id and not qname:
                self._debug_symbol(symbol_name, language, "Checking for method call on a class property.")
                parts = symbol_name.split('.')
                if len(parts) == 2:
                    prop_name, meth_name = parts
                    calling_class = self._get_class_for_symbol(cursor, source_symbol_id)
                    if calling_class:
                        self._debug_symbol(symbol_name, language, f"Found calling class: {calling_class['qname']}")
                        prop_type = self._find_property_type_in_chain(cursor, calling_class['id'], prop_name)
                        if prop_type:
                            self._debug_symbol(symbol_name, language, f"Found property '{prop_name}' with type '{prop_type}'.")
                            # Now we have the type of the property, so we can find the method
                            # by constructing the qname and searching for it.
                            new_qname = f"{prop_type}.{meth_name}"
                            self._debug_symbol(symbol_name, language, f"Constructed new qname: {new_qname}")
                            query = base_query.format("cs.qname = ?")
                            params = (language, new_qname)
                            cursor.execute(query, params)
                            rows = cursor.fetchall()
                            if rows:
                                self._debug_symbol(symbol_name, language, "Found with property type resolution.")
                                return [{'id': row['id'], 'type_id': row['type_id'], 'qname': row['qname'], 'name': row['name']} for row in rows]

            self._debug_symbol(symbol_name, language, "Attempting LIKE qname match.")
            query = base_query.format("cs.qname LIKE ?")
            params = (language, f"%{symbol_name}")
            cursor.execute(query, params)
            rows = cursor.fetchall()
            if rows:
                self._debug_symbol(symbol_name, language, "Found with LIKE qname match.")
                return [{'id': row['id'], 'type_id': row['type_id'], 'qname': row['qname'], 'name': row['name']} for row in rows]
        
            # Fallback for dynamic languages: if qname is like `instance.method`,
            # try finding a symbol with the name `method`.
            self._debug_symbol(symbol_name, language, "Attempting fallback for dynamic languages.")
            parts = symbol_name.split('.')
            if len(parts) > 1:
                method_name = parts[-1]
                self._debug_symbol(symbol_name, language, f"Searching for method name: {method_name}")
                query = base_query.format("cs.name = ?")
                params = (language, method_name)
                cursor.execute(query, params)
                rows = cursor.fetchall()
                if rows:
                    self._debug_symbol(symbol_name, language, "Found with dynamic language fallback.")
                    return [{'id': row['id'], 'type_id': row['type_id'], 'qname': row['qname'], 'name': row['name']} for row in rows]
        
        # Then try simple name match
        self._debug_symbol(symbol_name, language, "Attempting simple name match.")
        query = base_query.format("cs.name = ?")
        params = (language, symbol_name)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        if rows:
                self._debug_symbol(symbol_name, language, "Found with simple name match.")
                return [{'id': row['id'], 'type_id': row['type_id'], 'qname': row['qname'], 'name': row['name']} for row in rows]

        # If still not found and source_symbol_id is provided, try resolving through inheritance
        if source_symbol_id:
            self._debug_symbol(symbol_name, language, "Attempting to resolve through inheritance.")
            calling_class = self._get_class_for_symbol(cursor, source_symbol_id)
            if calling_class:
                self._debug_symbol(symbol_name, language, f"Found calling class for inheritance check: {calling_class['qname']}")
                inheritance_chain = self._get_inheritance_chain(cursor, calling_class['id'])
                self._debug_symbol(symbol_name, language, f"Inheritance chain: {[c['qname'] for c in inheritance_chain]}")
                # Search for the method in the inheritance chain, from child to parent
                for class_symbol in inheritance_chain:
                    self._debug_symbol(symbol_name, language, f"Checking for method in class: {class_symbol['qname']}")
                    # Look for functions/methods within this class that match the symbol_name
                    cursor.execute("""
                        SELECT cs.id, cs.type_id, cs.qname, cs.name FROM code_symbols cs
                        JOIN relationships r ON cs.id = r.target_symbol_id
                        JOIN relationship_types rt ON r.type_id = rt.id
                        WHERE r.source_symbol_id = ? AND rt.name = 'contains_method' AND cs.name = ?
                    """, (class_symbol['id'], symbol_name))
                    method_rows = cursor.fetchall()
                    if method_rows:
                        self._debug_symbol(symbol_name, language, f"Found method in ancestor class: {class_symbol['qname']}")
                        # Found the method in an ancestor class
                        return [{'id': row['id'], 'type_id': row['type_id'], 'qname': row['qname'], 'name': row['name']} for row in method_rows]
        
        self._debug_symbol(symbol_name, language, "Symbol not found.")
        return []

    def _find_property_type_in_chain(self, cursor, class_id: int, prop_name: str) -> Optional[str]:
        inheritance_chain = self._get_inheritance_chain(cursor, class_id)
        for class_symbol in inheritance_chain:
            cursor.execute(
                "SELECT value FROM symbol_properties WHERE symbol_id = ? AND key = ?",
                (class_symbol['id'], prop_name)
            )
            row = cursor.fetchone()
            if row:
                return row['value']
        return None

    def _get_class_for_symbol(self, cursor, symbol_id: int) -> Optional[Dict]:
        """
        Finds the class symbol that contains the given method/function symbol.
        """
        cursor.execute("""
            SELECT cs_class.id, cs_class.name, cs_class.qname FROM code_symbols cs_class
            JOIN relationships r ON cs_class.id = r.source_symbol_id
            JOIN relationship_types rt ON r.type_id = rt.id
            WHERE r.target_symbol_id = ? AND rt.name = 'contains_method'
        """, (symbol_id,))
        row = cursor.fetchone()
        if row:
            return {'id': row['id'], 'name': row['name'], 'qname': row['qname']}
        return None

    def _get_inheritance_chain(self, cursor, class_symbol_id: int) -> List[Dict]:
        """
        Recursively builds the inheritance chain for a given class,
        starting from the class itself and going up to its ancestors.
        """
        chain = []
        
        # Add the starting class to the chain
        cursor.execute("SELECT id, name, qname FROM code_symbols WHERE id = ?", (class_symbol_id,))
        current_class = cursor.fetchone()
        if current_class:
            chain.append({'id': current_class['id'], 'name': current_class['name'], 'qname': current_class['qname']})
        else:
            return chain # Class not found

        # Find direct parent classes
        cursor.execute("""
            SELECT cs_parent.id, cs_parent.name, cs_parent.qname FROM code_symbols cs_parent
            JOIN relationships r ON cs_parent.id = r.target_symbol_id
            JOIN relationship_types rt ON r.type_id = rt.id
            WHERE r.source_symbol_id = ? AND rt.name = 'inherits'
        """, (class_symbol_id,))
        parent_rows = cursor.fetchall()

        for parent_row in parent_rows:
            parent_id = parent_row['id']
            # Recursively get the chain for each parent and extend the current chain
            chain.extend(self._get_inheritance_chain(cursor, parent_id))
        
        # Remove duplicates while preserving order (important for search order)
        seen_ids = set()
        unique_chain = []
        for item in chain:
            if item['id'] not in seen_ids:
                unique_chain.append(item)
                seen_ids.add(item['id'])
        return unique_chain

    def _create_relationship(self, cursor, source_id: int, target_id: int, rel_type: str, confidence: float = 1.0):
        cursor.execute("SELECT id FROM relationship_types WHERE name = ?", (rel_type,))
        type_id_row = cursor.fetchone()
        if not type_id_row:
            raise ValueError(f"Relationship type '{rel_type}' not found in database.")
        type_id = type_id_row[0]

        cursor.execute(
            "INSERT INTO relationships (source_symbol_id, target_symbol_id, type_id, confidence) VALUES (?, ?, ?, ?)",
            (source_id, target_id, type_id, confidence),
        )


class IndexBuilder:
    """Main builder class that coordinates all indexing components."""

    def __init__(self, db_service: DatabaseService, max_workers: Optional[int] = None, debug_options: Optional[DebugOptions] = None):
        """
        Initialize the index builder.

        Args:
            db_service: An instance of the DatabaseService.
            max_workers: Maximum number of worker threads for parallel processing.
        """
        self.db_service = db_service
        self.max_workers = max_workers
        self.debug_options = debug_options or DebugOptions()
        self.analyzer_manager = LanguageAnalyzerManager(debug_options=self.debug_options)
        self.resolver = RelationshipResolver(db_service, debug_options=self.debug_options)
        self.project_path = ""  # Initialize project_path
        self.symbol_cache = {}
        self.relationship_type_cache = RelationshipTypeCache(db_service)

    def build_index(self, project_path: str, generate_log_file: bool = False):
        """
        Build complete code index for a project.

        Args:
            project_path: Path to the project root directory
        """
        start_time = datetime.now()
        self.project_path = project_path  # Store for file path resolution

        try:
            # Step 1: Scan project directory
            scanner = ProjectScanner(project_path, generate_log_file)
            scan_result = scanner.scan_project()

            # Pass 1: Analyze files and populate symbols and unresolved relationships
            analysis_results = self._analyze_files(scan_result.file_list)
            self._populate_symbols_and_unresolved_relationships(analysis_results)

            # Pass 2: Resolve relationships
            self.resolver.resolve_relationships()

            end_time = datetime.now()
            analysis_time_ms = int((end_time - start_time).total_seconds() * 1000)

            print(f"Analysis complete in {analysis_time_ms}ms.")
            print(f"Files with errors: {self._collect_files_with_errors(analysis_results)}")
            print(f"Languages analyzed: {self._collect_analyzed_languages(analysis_results)}")

        except (OSError, IOError, ValueError, RuntimeError) as e:
            # Log the error, no fallback index to create
            print(f"Error building index for {project_path}: {e}")

    def _populate_symbols_and_unresolved_relationships(self, analysis_results: List[FileAnalysisResult]):
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        for result in analysis_results:
            file_id = self._get_or_create_file_symbol(cursor, result.file_info)

            # Create a symbol for the file itself, making it searchable
            file_symbol_info = SimpleNamespace(
                name=result.file_info.path,
                qname=result.file_info.path,
                line_start=0,
                line_end=0
            )
            self._get_or_create_symbol(cursor, file_id, file_symbol_info, "file")

            for a_class in result.classes:
                class_id = self._get_or_create_symbol(cursor, file_id, a_class, "class")
                for method in a_class.methods:
                    method_id = self._get_or_create_symbol(cursor, file_id, method, "function")
                    self._create_relationship(cursor, class_id, method_id, "contains_method")
                    for call in method.calls:
                        self._create_unresolved_relationship(cursor, method_id, call.name, target_qname=getattr(call, 'qname', None))

                for prop in a_class.properties:
                    if prop.type_name:
                        cursor.execute(
                            "INSERT INTO symbol_properties (symbol_id, key, value) VALUES (?, ?, ?)",
                            (class_id, prop.name, prop.type_name)
                        )

                for parent_class_name in a_class.inherits_from:
                    self._create_unresolved_relationship(cursor, class_id, parent_class_name, "inherits")


            for function in result.functions:
                source_id = self._get_or_create_symbol(cursor, file_id, function, "function")
                for call in function.calls:
                    self._create_unresolved_relationship(cursor, source_id, call.name, target_qname=getattr(call, 'qname', None))
                for ref in function.variable_references:
                    self._create_unresolved_relationship(cursor, source_id, ref.name, "references_variable", target_qname=ref.qname)

            for var in result.variables:
                self._get_or_create_symbol(cursor, file_id, var, "variable")
        
        # Invalidate cache after all inserts to unresolved_relationships for this batch
        # This ensures that if new relationship types were added, they are picked up
        # if more processing were to happen on the same connection/transaction.
        # For a single run, this might be less critical for _create_unresolved_relationship
        # itself, but it's good practice for cache consistency.
        self.relationship_type_cache.clear()
        conn.commit()

    def _create_unresolved_relationship(self, cursor, source_id: int, target_name: str, rel_type: str = "calls", target_qname: Optional[str] = None):
        type_id = self.relationship_type_cache.get_type_id(rel_type)

        if type_id is None:
            # Type not found in cache or DB, insert it
            cursor.execute("INSERT INTO relationship_types (name) VALUES (?)", (rel_type,))
            type_id = cursor.lastrowid
            # Clear the cache so it repopulates with the new type on next access
            self.relationship_type_cache.clear()

        cursor.execute(
            "INSERT INTO unresolved_relationships (source_symbol_id, target_name, target_qname, relationship_type_id) VALUES (?, ?, ?, ?)",
            (source_id, target_name, target_qname, type_id),
        )

    def _get_or_create_file_symbol(self, cursor, file_info: FileInfo) -> int:
        cursor.execute("SELECT id FROM files WHERE path = ?", (file_info.path,))
        row = cursor.fetchone()
        if row:
            return row[0]

        cursor.execute(
            "INSERT INTO files (path, size, line_count, modified_time, language) VALUES (?, ?, ?, ?, ?)",
            (
                file_info.path,
                file_info.size,
                0,
                file_info.modified_time,
                file_info.language,
            ),
        )
        return cursor.lastrowid

    def _get_or_create_symbol(
        self,
        cursor,
        file_id: int,
        symbol_info: Any,
        symbol_type: str,
    ) -> int:
        qname = symbol_info.qname
        name = symbol_info.name

        if (file_id, qname) in self.symbol_cache:
            return self.symbol_cache[(file_id, qname)]

        cursor.execute(
            "SELECT id FROM code_symbols WHERE file_id = ? AND qname = ?", (file_id, qname)
        )
        row = cursor.fetchone()
        if row:
            self.symbol_cache[(file_id, qname)] = row[0]
            return row[0]

        cursor.execute("SELECT id FROM symbol_types WHERE name = ?", (symbol_type,))
        type_id_row = cursor.fetchone()
        if not type_id_row:
            raise ValueError(f"Symbol type '{symbol_type}' not found in database.")
        type_id = type_id_row[0]

        cursor.execute(
            """
            INSERT INTO code_symbols (file_id, name, qname, type_id, line_start, line_end)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                name,
                qname,
                type_id,
                symbol_info.line_start,
                symbol_info.line_end,
            ),
        )
        symbol_id = cursor.lastrowid
        self.symbol_cache[(file_id, qname)] = symbol_id
        return symbol_id

    def _find_symbol(self, cursor, symbol_name: str) -> List[int]:
        # If symbol name contains a separator, it's likely a qualified name.
        if "." in symbol_name or "\\" in symbol_name or "::" in symbol_name:
            cursor.execute("SELECT id FROM code_symbols WHERE qname LIKE ?", (f"%{symbol_name}",))
        else:
            cursor.execute("SELECT id FROM code_symbols WHERE name = ?", (symbol_name,))
        rows = cursor.fetchall()
        return [row[0] for row in rows]

    def _create_relationship(self, cursor, source_id: int, target_id: int, rel_type: str, confidence: float = 1.0):
        type_id = self.relationship_type_cache.get_type_id(rel_type)

        if type_id is None:
            # Type not found in cache or DB, insert it
            cursor.execute("INSERT INTO relationship_types (name) VALUES (?)", (rel_type,))
            type_id = cursor.lastrowid
            # Clear the cache so it repopulates with the new type on next access
            self.relationship_type_cache.clear()

        cursor.execute(
            "INSERT INTO relationships (source_symbol_id, target_symbol_id, type_id, confidence) VALUES (?, ?, ?, ?)",
            (source_id, target_id, type_id, confidence),
        )



    def _analyze_files(self, file_list: List[FileInfo]) -> List[FileAnalysisResult]:
        """
        Analyze all files in parallel.

        Args:
            file_list: List of FileInfo objects to analyze

        Returns:
            List of FileAnalysisResult objects
        """
        analysis_results = []
        for file_info in file_list:
            analyzer = self.analyzer_manager.get_analyzer(file_info.path)
            if analyzer:
                try:
                    result = analyzer.analyze_file(os.path.join(self.project_path, file_info.path))
                    analysis_results.append(FileAnalysisResult(file_info, **result))
                except Exception as e:
                    print(f"Error analyzing file {file_info.path}: {e}")
                    analysis_results.append(FileAnalysisResult(file_info, analysis_errors=[str(e)]))
            else:
                analysis_results.append(FileAnalysisResult(file_info))

        return analysis_results

    def _read_file_content(self, file_path: str) -> Optional[str]:
        """
        Read content from a file.

        Args:
            file_path: Path to the file (relative to project root)

        Returns:
            File content as string, or None if unreadable
        """
        try:
            # Convert relative path to absolute based on project path
            if not os.path.isabs(file_path):
                full_path = os.path.join(self.project_path, file_path)
            else:
                full_path = file_path

            # Try different encodings
            encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']

            for encoding in encodings:
                try:
                    with open(full_path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue

            # If all encodings fail, return None
            return None

        except (OSError, PermissionError, FileNotFoundError):
            return None


    def _estimate_line_count(self, result: FileAnalysisResult) -> int:
        """Estimate line count from analysis result."""
        # If we have functions or classes, use their line ranges
        max_line = 0

        for func in result.functions:
            max_line = max(max_line, func.line_end)

        for cls in result.classes:
            max_line = max(max_line, cls.line_end)

        # If no functions/classes, try to get from language-specific data
        if max_line == 0:
            for lang_data in result.language_specific.values():
                if isinstance(lang_data, dict) and 'line_count' in lang_data:
                    max_line = max(max_line, lang_data['line_count'])

        return max_line if max_line > 0 else 1

    def _collect_files_with_errors(self, analysis_results: List[FileAnalysisResult]) -> List[str]:
        """Collect files that had analysis errors."""
        files_with_errors = []

        for result in analysis_results:
            if result.analysis_errors:
                files_with_errors.append(result.file_info.path)

        return files_with_errors

    def _collect_analyzed_languages(self, analysis_results: List[FileAnalysisResult]) -> List[str]:
        """Collect unique languages that were analyzed."""
        languages = set()

        for result in analysis_results:
            languages.add(result.file_info.language)

        return sorted(list(languages))

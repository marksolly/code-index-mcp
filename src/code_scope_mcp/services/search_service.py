"""
Search service for the Code Scope MCP server.

This service handles code search operations, search tool management,
and search strategy selection.
"""

import sqlite3
import json
from typing import Dict, Any, Optional, List, Tuple

from .base_service import BaseService
from ..db.database import DatabaseService
from ..utils import ValidationHelper
from ..indexing.models import FileInfo, FunctionInfo, ClassInfo, ImportInfo, FileAnalysisResult


class SearchService(BaseService):
    """
    Service for managing code search operations.

    This service handles:
    - Code search with various parameters and options
    - Search tool management and detection
    - Search strategy selection and optimization
    - Search capabilities reporting
    """
    def __init__(self, ctx: "ContextHelper", db_service: Optional[DatabaseService] = None):
        super().__init__(ctx)
        self._db_service = db_service

    
    def search_code(  # pylint: disable=too-many-arguments
        self,
        pattern: str,
        case_sensitive: bool = True,
        context_lines: int = 0,
        file_pattern: Optional[str] = None,
        fuzzy: bool = False,
        regex: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Search for code patterns in the project.

        Handles the logic for search_code_advanced MCP tool.

        Args:
            pattern: The search pattern
            case_sensitive: Whether search should be case-sensitive
            context_lines: Number of context lines to show
            file_pattern: Glob pattern to filter files
            fuzzy: Whether to enable fuzzy matching
            regex: Regex mode - True/False to force, None for auto-detection

        Returns:
            Dictionary with search results or error information

        Raises:
            ValueError: If project is not set up or search parameters are invalid
        """
        self._require_project_setup()

        # Import here to avoid circular dependency
        from ..search.base import is_safe_regex_pattern

        # Smart regex detection if regex parameter is None
        if regex is None:
            regex = is_safe_regex_pattern(pattern)
            if regex:
                print(f"Auto-detected regex pattern: {pattern}")

        # Validate search pattern
        error = ValidationHelper.validate_search_pattern(pattern, regex)
        if error:
            raise ValueError(error)

        # Validate file pattern if provided
        if file_pattern:
            error = ValidationHelper.validate_glob_pattern(file_pattern)
            if error:
                raise ValueError(f"Invalid file pattern: {error}")

        # Get search strategy from settings
        if not self.settings:
            raise ValueError("Settings not available")

        strategy = self.settings.get_preferred_search_tool()
        if not strategy:
            raise ValueError("No search strategies available")

        print(f"Using search strategy: {strategy.name}")

        try:
            results = strategy.search(
                pattern=pattern,
                base_path=self.base_path,
                case_sensitive=case_sensitive,
                context_lines=context_lines,
                file_pattern=file_pattern,
                fuzzy=fuzzy,
                regex=regex
            )
            from ..utils import ResponseFormatter
            return ResponseFormatter.search_results_response(results)
        except Exception as e:
            raise ValueError(f"Search failed using '{strategy.name}': {e}") from e

    
    def refresh_search_tools(self) -> str:
        """
        Refresh the available search tools.

        Handles the logic for refresh_search_tools MCP tool.

        Returns:
            Success message with available tools information

        Raises:
            ValueError: If refresh operation fails
        """
        if not self.settings:
            raise ValueError("Settings not available")

        self.settings.refresh_available_strategies()
        config = self.settings.get_search_tools_config()

        available = config['available_tools']
        preferred = config['preferred_tool']
        return f"Search tools refreshed. Available: {available}. Preferred: {preferred}."

    
    def get_search_capabilities(self) -> Dict[str, Any]:
        """
        Get information about search capabilities and available tools.

        Returns:
            Dictionary with search tool information and capabilities
        """
        if not self.settings:
            return {"error": "Settings not available"}

        config = self.settings.get_search_tools_config()

        capabilities = {
            "available_tools": config.get('available_tools', []),
            "preferred_tool": config.get('preferred_tool', 'basic'),
            "supports_regex": True,
            "supports_fuzzy": True,
            "supports_case_sensitivity": True,
            "supports_context_lines": True,
            "supports_file_patterns": True
        }

        return capabilities

    def find_symbols(
        self,
        pattern: str,
        match_mode: str = 'glob',
        case_sensitive: bool = False,
        symbol_type: Optional[List[str] | str] = None,
        path_pattern: Optional[str] = None,
        limit: int = 50,
        include_context: List[str] = None
    ) -> str:
        """
        Find code symbols matching the given pattern and return a formatted summary.

        Args:
            pattern: The main search string for the symbol name.
            match_mode: Defines how the pattern is interpreted ('glob' or 'regex').
            case_sensitive: Determines if pattern matching should be case-sensitive.
            symbol_type: Filters search to specific symbol types (e.g., 'function', 'class').
            path_pattern: Glob pattern to restrict search to specific files/directories.
            limit: Maximum number of matching symbols to return.
            include_context: Specifies which contextual information to include.

        Returns:
            A formatted string with search results.
        """
        self._require_project_setup()
        if not self.settings:
            raise ValueError("Settings not available")

        if include_context is None:
            include_context = ['all']

        db_service = self._db_service
        close_db_at_end = False
        if not db_service:
            db_service = DatabaseService(self.settings.get_db_path())
            db_service.connect()
            close_db_at_end = True
        
        conn = db_service.get_connection()

        output_lines = []
        try:
            # Build base query for symbols
            base_query = """
                SELECT cs.id, cs.name, st.name as symbol_type, f.path as file_path,
                       cs.line_start, cs.line_end
                FROM code_symbols cs
                JOIN symbol_types st ON cs.type_id = st.id
                JOIN files f ON cs.file_id = f.id
                WHERE 1=1
            """
            params = []

            # Add pattern matching
            if match_mode == 'glob':
                # Convert glob-style wildcards to SQL LIKE wildcards
                like_pattern = pattern.replace('*', '%').replace('?', '_')
                # The `COLLATE NOCASE` on the `name` column handles case-insensitivity automatically
                # for `LIKE` operations, so we don't need `LOWER()`.
                # We only need to add a pragma for case-sensitive matching.
                if case_sensitive:
                    # This is a temporary pragma for this query
                    conn.execute("PRAGMA case_sensitive_like = ON;")
                
                base_query += " AND cs.name LIKE ?"
                params.append(like_pattern)

                if case_sensitive:
                    # It's good practice to turn it off after the query
                    conn.execute("PRAGMA case_sensitive_like = OFF;")
            else:
                raise ValueError(f"Invalid match_mode: {match_mode}. Must be 'glob'.")

            # Add symbol type filter
            if symbol_type:
                if isinstance(symbol_type, str):
                    symbol_type = [symbol_type]
                placeholders = ','.join(['?'] * len(symbol_type))
                base_query += f" AND st.name IN ({placeholders})"
                params.extend(symbol_type)

            # Add path pattern filter
            if path_pattern:
                # Convert glob-style wildcards to SQL LIKE wildcards for consistency
                path_like_pattern = path_pattern.replace('*', '%').replace('?', '_')
                base_query += " AND f.path LIKE ?"
                params.append(path_like_pattern)

            base_query += " LIMIT ?"
            params.append(limit)

            cursor = conn.cursor()
            cursor.execute(base_query, params)
            symbols_data = cursor.fetchall()

            if not symbols_data:
                return "No symbols found matching your criteria."

            # Fetch context if needed
            symbol_ids = [str(row['id']) for row in symbols_data]
            placeholders = ','.join(['?'] * len(symbol_ids))

            properties_map = {}
            relationships_map = {'incoming': {}, 'outgoing': {}}

            if 'all' in include_context or 'properties' in include_context:
                prop_query = f"""
                    SELECT symbol_id, key, value
                    FROM symbol_properties
                    WHERE symbol_id IN ({placeholders})
                """
                cursor.execute(prop_query, symbol_ids)
                for row in cursor.fetchall():
                    if row['symbol_id'] not in properties_map:
                        properties_map[row['symbol_id']] = {}
                    properties_map[row['symbol_id']][row['key']] = row['value']

            if 'all' in include_context or 'relationships' in include_context:
                rel_query = f"""
                    SELECT r.source_symbol_id, r.target_symbol_id, rt.name as rel_type,
                           r.confidence, s_target.name as target_name,
                           s_target.type_id as target_type_id,
                           st_target.name as target_symbol_type
                    FROM relationships r
                    JOIN relationship_types rt ON r.type_id = rt.id
                    JOIN code_symbols s_target ON r.target_symbol_id = s_target.id
                    JOIN symbol_types st_target ON s_target.type_id = st_target.id
                    WHERE r.source_symbol_id IN ({placeholders})
                """
                cursor.execute(rel_query, symbol_ids)
                for row in cursor.fetchall():
                    source_id = row['source_symbol_id']
                    if source_id not in relationships_map['outgoing']:
                        relationships_map['outgoing'][source_id] = []
                    relationships_map['outgoing'][source_id].append({
                        'type': row['rel_type'],
                        'target_name': row['target_name'],
                        'target_type': row['target_symbol_type'],
                        'confidence': row['confidence']
                    })

                inv_rel_query = f"""
                    SELECT r.target_symbol_id, r.source_symbol_id, rt.name as rel_type,
                           r.confidence, s_source.name as source_name,
                           s_source.type_id as source_type_id,
                           st_source.name as source_symbol_type
                    FROM relationships r
                    JOIN relationship_types rt ON r.type_id = rt.id
                    JOIN code_symbols s_source ON r.source_symbol_id = s_source.id
                    JOIN symbol_types st_source ON s_source.type_id = st_source.id
                    WHERE r.target_symbol_id IN ({placeholders})
                """
                cursor.execute(inv_rel_query, symbol_ids)
                for row in cursor.fetchall():
                    target_id = row['target_symbol_id']
                    if target_id not in relationships_map['incoming']:
                        relationships_map['incoming'][target_id] = []
                    relationships_map['incoming'][target_id].append({
                        'type': row['rel_type'],
                        'source_name': row['source_name'],
                        'source_type': row['source_symbol_type'],
                        'confidence': row['confidence']
                    })

            # Format output
            for row in symbols_data:
                symbol_id = row['id']
                symbol_name = row['name']
                symbol_type_display = row['symbol_type']
                file_path = row['file_path']
                line_start = row['line_start']
                line_end = row['line_end']

                output_lines.append(f"[{symbol_type_display}] {symbol_name}")

                if symbol_type_display == 'file':
                    contains_query = """
                        SELECT cs.name, st.name as symbol_type
                        FROM code_symbols cs
                        JOIN symbol_types st ON cs.type_id = st.id
                        WHERE cs.file_id = (SELECT id FROM files WHERE path = ?)
                          AND cs.id != ?
                        ORDER BY st.name, cs.name
                    """
                    cursor.execute(contains_query, (file_path, symbol_id))
                    contained_symbols = cursor.fetchall()
                    if contained_symbols:
                        contains_groups = {}
                        for s in contained_symbols:
                            s_type = s['symbol_type']
                            if s_type not in contains_groups:
                                contains_groups[s_type] = []
                            contains_groups[s_type].append(s['name'])
                        
                        output_lines.append("  - Contains:")
                        for s_type, names in contains_groups.items():
                            output_lines.append(f"    - {s_type}: {', '.join(names)}")

                if ('all' in include_context or 'location' in include_context) and symbol_type_display != 'file':
                    output_lines.append(f"  |> in: {file_path}" + (f" (lines {line_start}-{line_end})" if line_start and line_end else ""))

                if 'all' in include_context or 'properties' in include_context:
                    if symbol_id in properties_map:
                        for key, value in properties_map[symbol_id].items():
                            try:
                                # Try to parse as JSON for pretty printing, otherwise use as is
                                parsed_value = json.loads(value)
                                output_lines.append(f"  - {key}: {json.dumps(parsed_value, indent=2)}")
                            except json.JSONDecodeError:
                                output_lines.append(f"  - {key}: {value}")
                
                if 'all' in include_context or 'relationships' in include_context:
                    if symbol_id in relationships_map['outgoing']:
                        rel_groups = {}
                        for rel in relationships_map['outgoing'][symbol_id]:
                            rel_type = rel['type']
                            if rel_type not in rel_groups:
                                rel_groups[rel_type] = []
                            
                            confidence_marker = " ?" if rel.get('confidence', 1.0) < 0.5 else ""
                            rel_groups[rel_type].append(f"{rel['target_name']}{confidence_marker}")

                        for rel_type, targets in rel_groups.items():
                            output_lines.append(f"  -> {rel_type}: {', '.join(targets)}")

                    if symbol_id in relationships_map['incoming']:
                        rel_groups = {}
                        for rel in relationships_map['incoming'][symbol_id]:
                            rel_type = rel['type']
                            
                            display_rel_type = rel_type
                            if rel_type == 'calls':
                                display_rel_type = 'called_by'
                            elif rel_type == 'instantiates':
                                display_rel_type = 'instantiated_by'
                            elif rel_type in ['inherits', 'declares_class_method']:
                                continue

                            if display_rel_type not in rel_groups:
                                rel_groups[display_rel_type] = []

                            confidence_marker = " ?" if rel.get('confidence', 1.0) < 0.5 else ""
                            rel_groups[display_rel_type].append(f"{rel['source_name']}{confidence_marker}")

                        for rel_type, sources in rel_groups.items():
                            output_lines.append(f"  <- {rel_type}: {', '.join(sources)}")
                
                output_lines.append("") # Add a blank line for readability

        except sqlite3.Error as e:
            output_lines.append(f"Database error: {e}")
        finally:
            if close_db_at_end:
                db_service.close()

        return "\n".join(output_lines).strip()

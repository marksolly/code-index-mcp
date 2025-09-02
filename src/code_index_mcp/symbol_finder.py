"""
Standalone Symbol Finder for Code Index MCP.

This module provides a standalone class for finding and reporting code symbols
with their relationships, independent of MCP server infrastructure.
"""

import sqlite3
import json
import re
import fnmatch
from typing import Optional, List, Dict, Any

from .db.database import DatabaseService


class SymbolFinder:
    """
    Standalone class for finding and reporting code symbols with relationships.

    This class provides the core functionality of the find_symbols MCP tool
    in a standalone, dependency-free implementation that only requires
    a DatabaseService instance.
    """

    def __init__(self, database_service: DatabaseService):
        """
        Initialize the SymbolFinder.

        Args:
            database_service: DatabaseService instance for database operations
        """
        self.db_service = database_service

    def find_symbols(
        self,
        pattern: str,
        match_mode: str = 'glob',
        case_sensitive: bool = False,
        symbol_type: Optional[List[str] | str] = None,
        path_pattern: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 50,
        include_context: List[str] = None
    ) -> str:
        """
        Find code symbols matching the given pattern and return a formatted summary.

        This method fetches one extra record beyond the specified limit to detect
        if more results are available. If the limit is exceeded, a warning message
        is displayed at the end of the output indicating that more results exist.

        Args:
            pattern: The main search string for the symbol name.
            match_mode: Defines how the pattern is interpreted ('glob' or 'regex').
            case_sensitive: Determines if pattern matching should be case-sensitive.
            symbol_type: Filters search to specific symbol types (e.g., 'function', 'class').
            path_pattern: Glob pattern to restrict search to specific files/directories.
            language: Programming language to filter by (e.g., 'python', 'javascript').
            limit: Maximum number of matching symbols to return in the output.
            include_context: Specifies which contextual information to include.

        Returns:
            A formatted string with search results. If more than 'limit' results
            are found, a warning message is appended to the output.

        Raises:
            ValueError: If parameters are invalid or database operations fail
        """
        # Validate inputs
        self._validate_parameters(pattern, match_mode, path_pattern, language)

        if include_context is None:
            include_context = ['all']

        # Ensure database connection
        if not self.db_service.conn:
            self.db_service.connect()

        conn = self.db_service.get_connection()
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

            # Add language filter
            if language:
                base_query += " AND f.language = ?"
                params.append(language)

            base_query += " ORDER BY f.language, st.name, cs.name"
            base_query += " LIMIT ?"
            params.append(limit + 1)

            cursor = conn.cursor()
            cursor.execute(base_query, params)
            symbols_data = cursor.fetchall()

            if not symbols_data:
                return "No symbols found matching your criteria."

            # Check if limit was exceeded (we fetched limit + 1)
            limit_exceeded = len(symbols_data) > limit
            if limit_exceeded:
                symbols_data = symbols_data[:limit]  # Truncate to original limit

            # Fetch context if needed
            symbol_ids = [str(row['id']) for row in symbols_data]
            placeholders = ','.join(['?'] * len(symbol_ids))

            properties_map = {}
            relationships_map = {'incoming': {}, 'outgoing': {}}

            # Always fetch relationships since functions and methods always need them
            rel_query = f"""
                SELECT r.source_symbol_id, r.target_symbol_id, rt.name as rel_type,
                       rt.outbound_display as display_rel_type,
                       r.confidence, s_target.name as target_name,
                       s_target.qname as target_qname,
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
                    'display_type': row['display_rel_type'] or row['rel_type'],  # Fallback to original if display is null
                    'target_name': row['target_name'],
                    'target_qname': row['target_qname'],
                    'target_type': row['target_symbol_type'],
                    'target_symbol_id': row['target_symbol_id'],
                    'confidence': row['confidence']
                })

            inv_rel_query = f"""
                SELECT r.target_symbol_id, r.source_symbol_id, rt.name as rel_type,
                       rt.inbound_display as display_rel_type,
                       r.confidence, s_source.name as source_name,
                       s_source.qname as source_qname,
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
                    'display_type': row['display_rel_type'] or row['rel_type'],  # Fallback to original if display is null
                    'source_name': row['source_name'],
                    'source_qname': row['source_qname'],
                    'source_type': row['source_symbol_type'],
                    'source_symbol_id': row['source_symbol_id'],
                    'confidence': row['confidence']
                })

            # Only fetch properties if needed
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

            # Format output
            for row in symbols_data:
                symbol_id = row['id']
                symbol_name = row['name']
                symbol_type_display = row['symbol_type']
                file_path = row['file_path']
                line_start = row['line_start']
                line_end = row['line_end']

                # For method symbols, include the class name if available
                display_name = symbol_name
                if symbol_type_display == 'method':
                    # Check for incoming 'declares_class_method' relationship to find the class
                    if symbol_id in relationships_map['incoming']:
                        for rel in relationships_map['incoming'][symbol_id]:
                            if rel['type'] == 'declares_class_method':
                                display_name = f"{rel['source_name']}.{symbol_name}"
                                break

                output_lines.append(f"[{symbol_type_display}] {display_name}")

                # File symbols now handled consistently through relationships like other symbol types
                # Class symbols also handled through relationships for consistency

                if ('all' in include_context or 'location' in include_context) and symbol_type_display != 'file':
                    output_lines.append(f"  in: {file_path}" + (f" (lines {line_start}-{line_end})" if line_start and line_end else ""))

                if 'all' in include_context or 'properties' in include_context:
                    if symbol_id in properties_map:
                        for key, value in properties_map[symbol_id].items():
                            try:
                                # Try to parse as JSON for pretty printing, otherwise use as is
                                parsed_value = json.loads(value)
                                output_lines.append(f"  - {key}: {json.dumps(parsed_value, indent=2)}")
                            except json.JSONDecodeError:
                                output_lines.append(f"  - {key}: {value}")

                # Always include relationships for functions and methods
                show_relationships = ('all' in include_context or 'relationships' in include_context or
                                    symbol_type_display in ['function', 'method'])

                if show_relationships:
                    if symbol_id in relationships_map['outgoing']:
                        rel_groups = {}
                        for rel in relationships_map['outgoing'][symbol_id]:
                            display_rel_type = rel.get('display_type', rel['type'])
                            if display_rel_type not in rel_groups:
                                rel_groups[display_rel_type] = []

                            confidence_marker = " ?" if rel.get('confidence', 1.0) < 0.5 else ""

                            # For calls relationships, use qualified names from database
                            if rel.get('type', '').startswith('calls_'):
                                target_qname = rel.get('target_qname') or rel['target_name']
                                rel_groups[display_rel_type].append(f"{target_qname}{confidence_marker}")
                            else:
                                rel_groups[display_rel_type].append(f"{rel['target_name']}{confidence_marker}")

                        for rel_type, targets in rel_groups.items():
                            output_lines.append(f"  {rel_type}: {', '.join(targets)}")

                    if symbol_id in relationships_map['incoming']:
                        rel_groups = {}
                        for rel in relationships_map['incoming'][symbol_id]:
                            display_rel_type = rel.get('display_type', rel['type'])

                            # Skip certain relationship types for inbound display
                            if rel['type'] in ['inherits', 'declares_class_method']:
                                continue

                            if display_rel_type not in rel_groups:
                                rel_groups[display_rel_type] = []

                            confidence_marker = " ?" if rel.get('confidence', 1.0) < 0.5 else ""

                            # For called by relationships, use qualified names from database
                            if rel.get('type', '').startswith('calls_'):
                                source_qname = rel.get('source_qname') or rel['source_name']
                                rel_groups[display_rel_type].append(f"{source_qname}{confidence_marker}")
                            else:
                                rel_groups[display_rel_type].append(f"{rel['source_name']}{confidence_marker}")

                        for rel_type, sources in rel_groups.items():
                            output_lines.append(f"  {rel_type}: {', '.join(sources)}")

                output_lines.append("") # Add a blank line for readability

        except sqlite3.Error as e:
            raise ValueError(f"Database error: {e}") from e

        # Add warning at the end if limit was exceeded
        if limit_exceeded:
            output_lines.append(f"Warning: Output truncated to first {limit} results.")

        return "\n".join(output_lines).strip()

    def _validate_parameters(self, pattern: str, match_mode: str, path_pattern: Optional[str], language: Optional[str] = None) -> None:
        """
        Validate input parameters.

        Args:
            pattern: Search pattern to validate
            match_mode: Match mode to validate
            path_pattern: Path pattern to validate (optional)
            language: Language to validate (optional)

        Raises:
            ValueError: If any parameter is invalid
        """
        # Validate search pattern
        error = self._validate_search_pattern(pattern)
        if error:
            raise ValueError(error)

        # Validate match mode
        if match_mode not in ['glob', 'regex']:
            raise ValueError(f"Invalid match_mode: {match_mode}. Must be 'glob' or 'regex'.")

        # Note: Only glob is currently implemented, regex would need additional work
        if match_mode == 'regex':
            raise ValueError("Regex match_mode is not yet implemented in standalone version.")

        # Validate path pattern if provided
        if path_pattern:
            error = self._validate_glob_pattern(path_pattern)
            if error:
                raise ValueError(f"Invalid path pattern: {error}")

        # Validate language if provided
        if language:
            error = self._validate_language(language)
            if error:
                raise ValueError(f"Invalid language: {error}")

    def _validate_search_pattern(self, pattern: str) -> Optional[str]:
        """
        Validate a search pattern.

        Args:
            pattern: The search pattern to validate

        Returns:
            Error message if validation fails, None if valid
        """
        if not pattern:
            return "Search pattern cannot be empty"

        return None

    def _validate_glob_pattern(self, pattern: str) -> Optional[str]:
        """
        Validate a glob pattern.

        Args:
            pattern: The glob pattern to validate

        Returns:
            Error message if validation fails, None if valid
        """
        if not pattern:
            return "Pattern cannot be empty"

        # Check for potentially dangerous patterns
        if pattern.startswith('/') or pattern.startswith('\\'):
            return "Pattern cannot start with path separator"

        # Test if the pattern is valid by trying to compile it
        try:
            # This will raise an exception if the pattern is malformed
            fnmatch.translate(pattern)
        except (ValueError, TypeError) as e:
            return f"Invalid glob pattern: {str(e)}"

        return None

    def _validate_language(self, language: str) -> Optional[str]:
        """
        Validate a programming language.

        Args:
            language: The language to validate

        Returns:
            Error message if validation fails, None if valid
        """
        if not language:
            return "Language cannot be empty"

        # Basic validation - could be expanded with a list of supported languages
        # For now, just ensure it's a non-empty string
        if not isinstance(language, str):
            return "Language must be a string"

        return None

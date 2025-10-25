"""
MCP Server for Code Scope Symbol Finder.

This module provides an MCP server that exposes the SymbolFinder functionality
as MCP tools, allowing integration with MCP-compatible clients like Cline, Kilo Code, and Claude Code.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import FastMCP

from .db.database import DatabaseService
from .symbol_finder import SymbolFinder


# Global cache for database services
db_services: Dict[str, DatabaseService] = {}


def get_db_service(db_path: str) -> DatabaseService:
    """Get or create a DatabaseService for the given path."""
    if db_path not in db_services:
        db_service = DatabaseService(db_path)
        db_service.connect()
        db_service.initialize_db()
        db_services[db_path] = db_service
    return db_services[db_path]


def main():
    """Main entry point for the MCP server."""
    app = FastMCP("code-scope-mcp")

    @app.tool()
    async def find_symbols(
        db_path: str,
        pattern: str,
        match_mode: str = "glob",
        case_sensitive: bool = False,
        symbol_type: Optional[List[str]] = None,
        path_pattern: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 50,
        include_context: Optional[List[str]] = None
    ) -> str:
        """
        Searches a pre-built index of this codebase for code symbols matching patterns. Faster and more comprehensive than search_files or list_code_definition_names.

        Prefer over search_files for structured symbol searches with type filtering (classes, functions) and relationship tracking (imports, calls); search_files is better for arbitrary text patterns or comments.

        Parameters:

        - db_path (required): Path to SQLite database file containing the code index.
        - pattern (required): Search pattern for symbol names; supports glob wildcards by default.
        - match_mode (optional, default 'glob'): Option 'glob' or 'regex' for pattern matching.
        - case_sensitive (optional, default false): Set true for case-sensitive matching.
        - symbol_type (optional, default null): List of symbol types e.g. ['class', 'function'] to include.
        - path_pattern (optional, default null): Glob pattern to limit search to specific files/directories.
        - language (optional, default null): Programming language name to filter by, all if null.
        - limit (optional, default 50): Max results to return.
        - include_context (optional, default null): List of context types to include e.g. ['definition', 'type'].

        Returns: Tagged symbols ([class] etc.) with file paths, definition locations, and relationship data (imports, calls, instantiations) for detailed codebase insights.

        """
        try:
            # Get database service
            db_service = get_db_service(db_path)

            # Create symbol finder
            finder = SymbolFinder(db_service)

            # Convert symbol_type list to appropriate format
            if symbol_type and len(symbol_type) == 1:
                symbol_type = symbol_type[0]

            # Call find_symbols
            result = finder.find_symbols(
                pattern=pattern,
                match_mode=match_mode,
                case_sensitive=case_sensitive,
                symbol_type=symbol_type,
                path_pattern=path_pattern,
                language=language,
                limit=limit,
                include_context=include_context
            )

            return result

        except Exception as e:
            return f"Error finding symbols: {str(e)}"

    # Run the server
    app.run()


if __name__ == "__main__":
    main()
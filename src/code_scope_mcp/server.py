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
        Find code symbols in a code index database matching specified criteria.

        Args:
            db_path: Required. Path to the SQLite database file containing the code index.
            pattern: Required. Search pattern for symbol names (supports glob wildcards like * and ?)
            match_mode: Optional. Pattern matching mode ('glob' or 'regex'), default 'glob'.
            case_sensitive: Optional. Whether pattern matching should be case-sensitive, default false.
            symbol_type: Optional. List of symbol types to filter by.
            path_pattern: Optional. Glob pattern to restrict search to specific files/directories.
            language: Optional. Programming language to filter by.
            limit: Optional. Maximum number of results to return, default 100.
            include_context: Optional. Context information to include in results.

        Returns:
            Formatted string with search results
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
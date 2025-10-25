#!/usr/bin/env python3
"""
Code Scope MCP CLI Tool

A command-line interface for indexing codebases and querying the resulting symbol database.

Examples:
  # Index a directory
  uv run python cli.py index /path/to/project

  # Index with custom database
  uv run python cli.py index /path/to/project --db-path my_index.db

  # Query for all functions
  uv run python cli.py query "*" --symbol-type function

  # Query with multiple filters
  uv run python cli.py query "User*" --symbol-type class --symbol-type function --path-pattern "src/**"

  # Query with context
  uv run python cli.py query "getUser" --include-context properties --include-context relationships
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple

# Add src to path for imports
project_root = Path(__file__).parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from code_scope_mcp.db.database import DatabaseService
from code_scope_mcp.indexing.orchestrator import IndexingOrchestrator
from code_scope_mcp.indexing.indexing_logger import IndexingLogger
from code_scope_mcp.indexing.ignore_handler import IgnoreHandler
from code_scope_mcp.symbol_finder import SymbolFinder


def build_extension_map() -> dict:
    """Build extension to language mapping from language definitions."""
    from code_scope_mcp.indexing.languages import LanguageDefinition
    import inspect

    extension_map = {}

    # Discover language definitions (same way as orchestrator)
    try:
        # Import the languages module
        import code_scope_mcp.indexing.languages as lang_module

        for name, obj in inspect.getmembers(lang_module):
            if (inspect.isclass(obj) and
                hasattr(obj, '__bases__') and
                any('LanguageDefinition' in str(base) for base in obj.__bases__)):
                try:
                    definition = obj()
                    if hasattr(definition, 'file_extensions'):
                        for ext in definition.file_extensions:
                            extension_map[ext] = definition.language_name
                except Exception:
                    continue
    except ImportError:
        pass

    return extension_map


def scan_directory(target_dir: str, ignore_handler: IgnoreHandler) -> List[str]:
    """Scan directory for files and return a list of file paths to index."""
    extension_map = build_extension_map()
    files_to_index = []
    ignored_files = 0
    ignored_dirs = 0

    print(f"Scanning directory: {target_dir}")

    for root, dirs, files in os.walk(target_dir):
        # Filter directories in-place to avoid walking ignored dirs
        original_dirs_count = len(dirs)
        dirs[:] = [d for d in dirs if not ignore_handler.is_ignored(os.path.join(root, d))]
        ignored_dirs += original_dirs_count - len(dirs)

        for file in files:
            file_path = os.path.join(root, file)

            if ignore_handler.is_ignored(file_path):
                ignored_files += 1
                continue

            # Check extension
            _, ext = os.path.splitext(file)
            if ext in extension_map:
                files_to_index.append(file_path)

    ignore_summary = ""
    if ignored_files or ignored_dirs:
        ignore_parts = []
        if ignored_files:
            ignore_parts.append(f"{ignored_files} file{'s' if ignored_files != 1 else ''}")
        if ignored_dirs:
            ignore_parts.append(f"{ignored_dirs} director{'ies' if ignored_dirs != 1 else 'y'}")
        ignore_summary = f" ({', '.join(ignore_parts)} ignored)"

    print(f"Total files to index: {len(files_to_index)}{ignore_summary}")
    return files_to_index


def cmd_index(args):
    """Handle the index command."""
    target_dir = Path(args.directory).resolve()
    db_path = Path(args.db_path or "code_index.db").resolve()

    if not target_dir.exists():
        print(f"Error: Directory {target_dir} does not exist")
        return 1

    if not target_dir.is_dir():
        print(f"Error: {target_dir} is not a directory")
        return 1

    print(f"Indexing directory: {target_dir}")
    print(f"Database: {db_path}")

    # Setup database
    db_service = DatabaseService(str(db_path))
    db_service.delete_db()  # Start fresh
    db_service.initialize_db()

    # Setup ignore handler for both scanning and orchestrator
    ignore_handler = IgnoreHandler()

    # Scan directory
    files_to_index = scan_directory(str(target_dir), ignore_handler)

    # Report ignore rules used (always show for transparency)
    registry = ignore_handler.get_registry()
    if registry:
        ignore_files_str = ", ".join(sorted(registry))
        print(f"Ignore rules applied from: {ignore_files_str}")
    else:
        print("Using default ignore rules. Create an .indexerignore file to override default exclusions. See README for details.")

    if not files_to_index:
        print("No files found to index")
        return 0

    # Setup orchestrator with profiling if requested
    logger_filters = {
        'component_names' : ['Orchestrator']
    }
    logger = IndexingLogger(enabled=True, filters=logger_filters)

    # Enable profiling if requested
    if args.profile:
        logger.enable_profiling()
        print("🔍 Profiling enabled - will show detailed performance metrics")

    # Enable exception catching for production robustness
    # Set exception log file next to the database file
    exception_log_file = str(db_path) + ".exceptions.log"
    orchestrator = IndexingOrchestrator(
        db_service,
        logger,
        catch_exceptions=True,
        exception_log_file=exception_log_file,
        ignore_handler=ignore_handler
    )

    # Process files
    print("Starting indexing process...")
    orchestrator.process_files(files_to_index)

    print(f"Indexing complete. Database saved to: {db_path}")
    return 0


def parse_csv_list(values):
    """Parse a list that may contain comma-separated values."""
    if not values:
        return None

    result = []
    for value in values:
        if ',' in value:
            # Split by comma and strip whitespace
            result.extend([v.strip() for v in value.split(',') if v.strip()])
        else:
            result.append(value)
    return result


def get_available_symbol_types():
    """Get available symbol types from the database."""
    try:
        # Try to connect to existing database to get current symbol types
        db_path = Path("code_index.db")
        if db_path.exists():
            db_service = DatabaseService(str(db_path))
            db_service.connect()
            conn = db_service.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM symbol_types ORDER BY name")
            types = [row[0] for row in cursor.fetchall()]
            cursor.close()
            db_service.close()
            if types:
                return types
    except Exception:
        pass

    # Fallback to default types if database not available
    return ['class', 'function', 'method', 'constant', 'file', 'import', 'global', 'variable', 'export', 'namespace']


def cmd_update(args):
    """Handle the update command for incremental indexing."""
    db_path = Path(args.db_path or "code_index.db").resolve()

    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist. Run 'index' command first.")
        return 1

    # Validate target paths
    target_paths = []
    for path_str in args.paths:
        target_path = Path(path_str).resolve()

        if not target_path.exists():
            print(f"Error: Path {target_path} does not exist")
            return 1

        target_paths.append(str(target_path))

    print("Incremental update for paths:", target_paths)
    print(f"Database: {db_path}")

    # Setup database
    db_service = DatabaseService(str(db_path))
    db_service.connect()

    # Setup logger
    logger_filters = {
        'component_names' : ['Orchestrator']
    }
    logger = IndexingLogger(enabled=True, filters=logger_filters)

    # Enable exception catching for production robustness
    exception_log_file = str(db_path) + ".update.exceptions.log"
    orchestrator = IndexingOrchestrator(
        db_service,
        logger,
        incremental_mode=True,  # Enable incremental mode
        catch_exceptions=True,
        exception_log_file=exception_log_file
    )

    # Process files incrementally
    print("Starting incremental update...")
    try:
        orchestrator.process_files(target_paths)
        print(f"Incremental update complete. Database updated: {db_path}")
        return 0
    except Exception as e:
        print(f"Error during incremental update: {e}")
        return 1


def cmd_query(args):
    """Handle the query command."""
    db_path = Path(args.db_path or "code_index.db").resolve()

    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist. Run 'index' command first.")
        return 1

    # Setup database
    db_service = DatabaseService(str(db_path))
    db_service.connect()

    # Setup symbol finder
    finder = SymbolFinder(db_service)

    # Prepare arguments - handle CSV and multiple args
    symbol_type = parse_csv_list(args.symbol_type)
    include_context = parse_csv_list(args.include_context)

    # Execute query
    try:
        result = finder.find_symbols(
            pattern=args.pattern,
            match_mode=args.match_mode,
            case_sensitive=args.case_sensitive,
            symbol_type=symbol_type,
            path_pattern=args.path_pattern,
            language=args.language,
            limit=args.limit,
            include_context=include_context
        )

        print(result)
        return 0

    except ValueError as e:
        print(f"Error: {e}")
        return 1


def main():
    # Get available symbol types for help text
    available_types = get_available_symbol_types()
    symbol_types_str = ', '.join(available_types)

    parser = argparse.ArgumentParser(
        description="Code Scope MCP CLI Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  # Index a directory
  uv run python cli.py index /path/to/project

  # Index with custom database
  uv run python cli.py index /path/to/project --db-path my_index.db

  # Query for all classes
  uv run python cli.py query "*" --symbol-type class

  # Query with multiple filters
  uv run python cli.py query "User*" --symbol-type class --symbol-type function --path-pattern "src/**"

  # Query with context
  uv run python cli.py query "getUser" --include-context properties --include-context relationships

SYMBOL TYPES:
  Available: {symbol_types_str}

PATTERN MATCHING:
  The 'pattern' parameter searches symbol names using glob-style wildcards (*, ?).
  Examples: "User*", "*Handler", "get_*", "Base*"

USAGE NOTES:
  - Use --symbol-type multiple times to search multiple types
  - --symbol-type also supports comma-separated values: --symbol-type "class,function"
  - Pattern "*" matches all symbols of the specified type(s)
  - File paths use glob patterns (e.g., "src/**" matches all files in src/)
  - Language filter uses exact matches (e.g., "python", "javascript")
  - File paths use glob patterns (e.g., "src/**" matches all files in src/)
  - Language filter uses exact matches (e.g., "python", "javascript")
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Index command
    index_parser = subparsers.add_parser('index', help='Index a directory')
    index_parser.add_argument('directory', help='Directory to index')
    index_parser.add_argument('--db-path', help='Path to database file (default: code_index.db)')
    index_parser.add_argument('--profile', action='store_true', help='Enable profiling to measure database vs total indexing time')
    index_parser.set_defaults(func=cmd_index)

    # Update command
    update_parser = subparsers.add_parser('update', help='Incrementally update index for specific files')
    update_parser.add_argument('paths', nargs='+', help='Files or directories to update')
    update_parser.add_argument('--db-path', help='Path to database file (default: code_index.db)')
    update_parser.set_defaults(func=cmd_update)

    # Query command
    query_parser = subparsers.add_parser('query', help='Query the index')
    query_parser.add_argument('pattern', help='Search pattern')
    query_parser.add_argument('--db-path', help='Path to database file (default: code_index.db)')
    query_parser.add_argument('--match-mode', choices=['glob', 'regex'],
                             default='glob', help='Pattern matching mode (default: glob)')
    query_parser.add_argument('--case-sensitive', action='store_true',
                             help='Case sensitive matching')
    query_parser.add_argument('--symbol-type', action='append',
                             help='Filter by symbol type (can be used multiple times)')
    query_parser.add_argument('--path-pattern', help='Filter by file path pattern')
    query_parser.add_argument('--language', help='Filter by programming language (e.g., python, javascript)')
    query_parser.add_argument('--limit', type=int, default=50,
                             help='Maximum number of results (default: 50)')
    query_parser.add_argument('--include-context', action='append',
                             choices=['all', 'properties', 'relationships', 'location'],
                             help='Context to include (can be used multiple times, default: all)')
    query_parser.set_defaults(func=cmd_query)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())

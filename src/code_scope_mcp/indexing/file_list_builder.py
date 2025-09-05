import os
from pathlib import Path
from typing import List, Tuple

from .ignore_handler import IgnoreHandler
from .indexing_logger import IndexingLogger
from .languages import LanguageDefinition


class FileListBuilder:
    """
    Handles file list preparation logic for indexing, including incremental mode
    scanning, database queries for deletions, and related file discovery.

    Intended to be consumed by IndexingOrchestrator.
    """

    def __init__(self, logger: IndexingLogger, db_connection, incremental_mode: bool):
        self.logger = logger
        self.db_connection = db_connection
        self.incremental_mode = incremental_mode
        # Create a temporary ignore handler (will be passed from orchestrator in future)
        self.ignore_handler = None  # Will be set when prepare() is called

    def prepare(self, input_list: List[str], ignore_handler: IgnoreHandler) -> Tuple[List[str], List[str], List[str]]:
        """
        Prepare valid file paths and delete file paths based on input list.
        Follows the specified logic flow:
        1. Separate input into files vs directories
        2. If incremental_mode: scan directories, query DB for deletions, discover related files
        3. Process all directories to build complete file list
        4. Apply ignore handler and extension filtering
        5. Return valid_file_paths, delete_file_paths

        Args:
            input_list: List of file paths or directory paths to process
            ignore_handler: Ignore handler for filtering files

        Returns:
            Tuple of (valid_file_paths, delete_file_paths)
        """
        self.ignore_handler = ignore_handler

        # Separate input into files vs directories
        input_dirs, interim_file_list = self._separate_files_and_dirs(input_list)

        delete_file_paths = []
        extant_list = []

        if self.incremental_mode:
            # Recursively scan directories building extant_list
            for directory in input_dirs:
                if os.path.exists(directory) and os.path.isdir(directory):
                    self._scan_directory_recursive(directory, extant_list)

            # Query DB for indexed paths matching directory prefixes
            indexed_paths = self._query_indexed_paths(input_dirs)

            # Find deletions = indexed_paths not in extant_list
            delete_file_paths = [path for path in indexed_paths if path not in extant_list]

            # Discover related files for both scanned directories AND input files
            all_files_to_check = list(extant_list)
            for file_path in interim_file_list:
                if file_path not in all_files_to_check:
                    all_files_to_check.append(file_path)

            # Single-level dependency discovery (no recursion to avoid performance issues)
            for file_path in all_files_to_check:
                related_files = self.discover_related_files([file_path])
                for related_path, _, _ in related_files:
                    if related_path not in interim_file_list:
                        interim_file_list.append(related_path)

        # Process directories to build complete file list
        for directory in input_dirs:
            if os.path.exists(directory) and os.path.isdir(directory):
                self._scan_directory_recursive(directory, interim_file_list)

        # Ensure uniqueness
        interim_file_list = list(set(interim_file_list))

        # Apply ignore handler and build valid_file_paths with logging
        valid_file_paths = []
        scan_log = []

        for file_path in interim_file_list:
            if self.ignore_handler.is_ignored(file_path):
                print(f"- {file_path}")
                continue

            # Check if it's a supported file type
            _, ext = os.path.splitext(file_path)
            if not self._is_supported_extension(ext):
                print(f"- {file_path} (unsupported)")
                continue

            print(f"+ {file_path}")
            valid_file_paths.append(file_path)

        # Apply pseudo-deterministic shuffle for reproducible non-deterministic ordering
        # This ensures the ordering isn't fully deterministic (to test import resolution robustness)
        # but is consistent across test runs (for test reliability)
        #valid_file_paths = self._pseudo_shuffle(valid_file_paths)
        #for file_path in valid_file_paths:
        #    print(f"+ {file_path}")

        # Return three lists: valid_files, delete_files, primary_targets
        return valid_file_paths, delete_file_paths, interim_file_list

    def _separate_files_and_dirs(self, input_list: List[str]) -> Tuple[List[str], List[str]]:
        """Separate input list into directories and files."""
        input_dirs = []
        interim_file_list = []

        for item in input_list:
            if os.path.isdir(item):
                input_dirs.append(item)
            elif os.path.isfile(item):
                interim_file_list.append(item)

        return input_dirs, interim_file_list

    def _scan_directory_recursive(self, directory: str, file_list: List[str]):
        """
        Recursively scan directory building file list with smart ignore filtering.
        Applies ignore rules to directories before recursing to avoid unnecessary traversal.
        """
        try:
            for root, dirs, files in os.walk(directory):
                # Filter directories in-place before recursing
                original_dirs = dirs[:]
                dirs[:] = [d for d in dirs if not self.ignore_handler.is_ignored(os.path.join(root, d))]
                for d in original_dirs:
                    if d not in dirs:
                        print(f"- {os.path.join(root, d)}")

                for file in files:
                    file_path = os.path.join(root, file)
                    # Apply ignore rules to individual files
                    if self.ignore_handler.is_ignored(file_path):
                        print(f"- {file_path}")
                    else:
                        file_list.append(file_path)
        except PermissionError:
            self.logger.log("FileListBuilder", f"Permission denied accessing directory: {directory}")

    def _query_indexed_paths(self, input_dirs: List[str]) -> List[str]:
        """Query database for indexed paths matching directory prefixes."""
        indexed_paths = []

        cursor = self.db_connection.cursor()
        try:
            for directory in input_dirs:
                # Use LIKE query to find all paths starting with this directory prefix
                cursor.execute("SELECT path FROM files WHERE path LIKE ?", (f"{directory}%",))
                rows = cursor.fetchall()
                for row in rows:
                    indexed_paths.append(row['path'])
        finally:
            cursor.close()

        return indexed_paths

    def _is_supported_extension(self, extension: str) -> bool:
        """Check if file extension is supported using the proper extension mapping."""
        extension_map = self._build_extension_map()
        return extension in extension_map

    def _build_extension_map(self) -> dict:
        """Build extension to language mapping from language definitions."""
        extension_map = {}

        # Import the languages module
        from . import languages as lang_module
        import inspect

        # Discover language definitions (same way as orchestrator)
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

        return extension_map

    def discover_related_files(self, lookup_file_paths: List[str]) -> List[Tuple[str, str, str]]:
        """
        Discover files that have relationships with the lookup files.
        Uses ANY first-degree relationship to find related files that may need re-indexing.
        Returns a list of (file_path, language, content) tuples for discovery of related files.

        Moved from IndexingOrchestrator._discover_related_files
        """
        if not lookup_file_paths:
            return []

        cursor = self.db_connection.cursor()
        try:
            # Create temporary table for lookup files
            cursor.execute("CREATE TEMPORARY TABLE lookup_files_temp (file_id INTEGER PRIMARY KEY)")
            # Batch insert lookup file paths
            placeholders = ",".join("?" for _ in lookup_file_paths)
            cursor.execute(f"""
                INSERT INTO lookup_files_temp (file_id)
                SELECT id FROM files WHERE path IN ({placeholders})
            """, lookup_file_paths)

            # Unified dependency discovery query - ANY first-degree relationship
            cursor.execute("""
                SELECT DISTINCT related_file.path, related_file.language, NULL as content_placeholder
                FROM relationships r
                JOIN code_symbols AS source_symbol ON r.source_symbol_id = source_symbol.id
                JOIN code_symbols AS target_symbol ON r.target_symbol_id = target_symbol.id
                JOIN files AS source_file ON source_symbol.file_id = source_file.id
                JOIN files AS related_file ON source_symbol.file_id = related_file.id
                WHERE target_symbol.file_id IN (SELECT file_id FROM lookup_files_temp)

                UNION

                SELECT DISTINCT related_file.path, related_file.language, NULL as content_placeholder
                FROM relationships r
                JOIN code_symbols AS source_symbol ON r.source_symbol_id = source_symbol.id
                JOIN code_symbols AS target_symbol ON r.target_symbol_id = target_symbol.id
                JOIN files AS source_file ON source_symbol.file_id = source_file.id
                JOIN files AS related_file ON target_symbol.file_id = related_file.id
                WHERE source_symbol.file_id IN (SELECT file_id FROM lookup_files_temp)
            """)

            results = cursor.fetchall()

            related_files = []
            for row in results:
                file_path = row[0]
                # Only include files that exist and are not already in our lookup file set
                if os.path.exists(file_path) and file_path not in lookup_file_paths:
                    related_files.append((file_path, row[1] or 'unknown', ''))  # Empty content, will be loaded later
            return related_files

        finally:
            cursor.close()
            # Clean up temp table
            try:
                cursor = self.db_connection.cursor()
                cursor.execute("DROP TABLE IF EXISTS lookup_files_temp")
                cursor.close()
            except:
                pass  # Ignore cleanup errors

    def _pseudo_shuffle(self, file_list: List[str], no_initial_sort: bool = False) -> List[str]:
        """
        Apply a deterministic shuffle to create pseudo-random ordering.
        This ensures consistent non-deterministic behavior across test runs
        by using a hash-based shuffle that depends on the input list content.

        Args:
            file_list: List of file paths to shuffle

        Returns:
            Pseudo-randomly ordered list (deterministic for same input)
        """
        
        from collections import deque

        if no_initial_sort:
            file_list = deque(file_list)    
        else:
            file_list = deque(sorted(file_list))
        
        new_list = []

        while file_list:
            new_list.append(file_list.pop())  # Take from end
            if file_list:
                new_list.append(file_list.popleft())  # Take from start


        return new_list

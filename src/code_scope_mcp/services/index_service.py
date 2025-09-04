"""
Index management service for the Code Scope MCP server.

This service handles index building, management, file discovery,
and index refresh operations.
"""

import fnmatch
import json
import logging
import os
import threading
import time
import traceback
from typing import Dict, Any
from mcp.server.fastmcp import Context

from .base_service import BaseService
from ..utils import ValidationHelper


class IndexService(BaseService):
    """
    Service for managing project indexing and file discovery.

    This service handles:
    - Index building and rebuilding
    - File discovery and pattern matching
    - Index refresh operations
    - Index statistics and metadata
    """

    def __init__(self, ctx: Context):
        """
        Initialize the index service.

        Args:
            ctx: The MCP Context object
        """
        super().__init__(ctx)
        self.logger = logging.getLogger(__name__)
        self.is_rebuilding = False
        self._rebuild_lock = threading.Lock()
        self._executor = None

    def rebuild_index(self) -> str:
        """
        Rebuild the project index.

        Handles the logic for refresh_index MCP tool.

        Returns:
            Success message with file count information

        Raises:
            ValueError: If project is not set up or rebuild fails
        """
        self._require_project_setup()

        # Clear the entire database before a full rebuild
        db_path = self.settings.get_db_path()
        db_service = DatabaseService(db_path)
        db_service.connect()
        try:
            cursor = db_service.get_connection().cursor()
            # Clear all tables, respecting foreign key constraints
            cursor.execute("DELETE FROM relationships;")
            cursor.execute("DELETE FROM symbol_properties;")
            cursor.execute("DELETE FROM code_symbols;")
            cursor.execute("DELETE FROM files;")
            db_service.get_connection().commit()
            cursor.close()
        finally:
            db_service.close()

        # Re-index the project
        file_count = self._index_project(self.base_path)

        # Update the last indexed timestamp in config
        if self.settings:
            config = self.settings.load_config()
            self.settings.save_config({
                **config,
                'last_indexed': time.time()
            })


        return f"Project re-indexed. Found {file_count} files."

    def find_files_by_pattern(self, pattern: str) -> Dict[str, Any]:
        """
        Find files matching a glob pattern.

        Simplified version - file watcher handles all index updates proactively.

        Args:
            pattern: Glob pattern to match files against

        Returns:
            Dictionary with files list and status information

        Raises:
            ValueError: If project is not set up or pattern is invalid
        """
        from ..utils import ResponseFormatter
        self._require_project_setup()

        # Validate glob pattern
        error = ValidationHelper.validate_glob_pattern(pattern)
        if error:
            raise ValueError(error)

        # Check if we need to index the project initially
        if not self.index_cache:
            self._index_project(self.base_path)

        # Search using directory tree
        matching_files = []
        if self.index_cache and 'directory_tree' in self.index_cache:
            matching_files = self._search_directory_tree(
                self.index_cache['directory_tree'],
                pattern,
                ""
            )

        # Return results - file watcher now handles all index updates proactively
        return ResponseFormatter.file_list_response(
            matching_files,
            f"✅ Found {len(matching_files)} files"
        )

    def get_index_stats(self) -> Dict[str, Any]:
        """
        Get index statistics and metadata.

        Returns:
            Dictionary with index statistics

        Raises:
            ValueError: If project is not set up
        """
        self._require_project_setup()

        stats = {
            "file_count": self.file_count,
            "base_path": self.base_path,
            "index_available": bool(self.index_cache),
            "has_directory_tree": ('directory_tree' in self.index_cache
                                   if self.index_cache else False),
            "has_files_list": 'files' in self.index_cache if self.index_cache else False
        }

        if self.index_cache and 'project_metadata' in self.index_cache:
            stats.update(self.index_cache['project_metadata'])

        return stats

    def update_file(self, file_path: str, db_service=None):
        """
        Update the index for a single file.
        Deletes existing data and re-indexes the file.
        """
        self.logger.info(f"Incrementally updating index for: {file_path}")

        close_db_service = False
        if db_service is None:
            db_path = self.settings.get_db_path()
            db_service = DatabaseService(db_path)
            db_service.connect()
            close_db_service = True
        
        try:
            # First, remove existing data for this file
            self.remove_file(file_path, db_service)

            # Now, re-index the single file
            from ..indexing import IndexBuilder
            from ..indexing.scanner import get_file_info
            
            builder = IndexBuilder(db_service)
            builder.project_path = self.base_path

            try:
                file_info = get_file_info(self.base_path, file_path)
                if file_info:
                    analysis_results = builder._analyze_files([file_info])
                    builder.graph_builder.build_graph(analysis_results)
                    self.logger.info(f"Successfully updated index for: {file_path}")
                else:
                    self.logger.warning(f"Could not get file info for: {file_path}, skipping update.")
            
            except FileNotFoundError:
                self.logger.warning(f"File not found during update: {file_path}, assuming it was deleted.")
                self.remove_file(file_path, db_service)
            except Exception as e:
                self.logger.error(f"Error updating index for {file_path}: {e}")

        finally:
            if close_db_service:
                db_service.close()

    def remove_file(self, file_path: str, db_service=None):
        """
        Remove all data associated with a file from the database.
        """
        self.logger.info(f"Removing all data for file: {file_path}")
        
        close_db_service = False
        if db_service is None:
            db_path = self.settings.get_db_path()
            db_service = DatabaseService(db_path)
            db_service.connect()
            close_db_service = True

        try:
            conn = db_service.get_connection()
            cursor = conn.cursor()
            # The ON DELETE CASCADE foreign key will handle deleting related symbols and relationships
            cursor.execute("DELETE FROM files WHERE path = ?", (file_path,))
            conn.commit()
            cursor.close()
            self.logger.info(f"Successfully removed data for file: {file_path}")
        except Exception as e:
            self.logger.error(f"Error removing file data for {file_path}: {e}")
        finally:
            if close_db_service:
                db_service.close()

    def _index_project(self, base_path: str) -> int:
        """
        Build the project index using the IndexBuilder system.

        Args:
            base_path: The project base path

        Returns:
            Number of files indexed
        """
        from ..indexing import IndexBuilder
        from ..db.database import DatabaseService

        print(f"Building index for project: {base_path}")

        db_path = self.settings.get_db_path()
        db_service = DatabaseService(db_path)
        db_service.connect()
        db_service.initialize_db()

        try:
            builder = IndexBuilder(db_service)
            builder.build_index(base_path)

            # Get the file count from the database
            cursor = db_service.get_connection().cursor()
            cursor.execute("SELECT COUNT(*) FROM files")
            file_count = cursor.fetchone()[0]
            cursor.close()

            print(f"Index built successfully with {file_count} files")
            return file_count

        finally:
            db_service.close()

    def start_background_rebuild(self) -> bool:
        """
        Start index rebuild in background without blocking searches.
        
        This method can be called from any thread (including file watcher threads).
        Uses a persistent ThreadPoolExecutor with proper concurrency control.
        
        Returns:
            True if rebuild started, False if already in progress
        """
        self.logger.debug("start_background_rebuild called")
        
        # Atomic check-and-set with proper locking
        with self._rebuild_lock:
            if self.is_rebuilding:
                self.logger.debug("Rebuild already in progress, skipping")
                return False
            
            # Atomically set rebuilding flag
            self.is_rebuilding = True
        
        try:
            import concurrent.futures
            
            # Initialize executor if needed
            if self._executor is None:
                self._executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=1, 
                    thread_name_prefix="index_rebuild"
                )
                self.logger.debug("Created persistent ThreadPoolExecutor for rebuilds")
            
            self.logger.debug("Starting background rebuild in thread pool")
            
            def run_sync_rebuild():
                """Run the rebuild synchronously in a background thread."""
                try:
                    start_time = time.time()
                    self.logger.debug("Starting sync index rebuild...")
                    
                    # Build new index using existing sync logic
                    file_count = self._index_project(self.base_path)
                    
                    duration = time.time() - start_time
                    self.logger.info("Background rebuild completed in %.2fs with %d files", 
                                    duration, file_count)
                    
                    return True
                    
                except Exception as e:
                    self.logger.error("Background rebuild failed: %s", e)
                    self.logger.error("Traceback: %s", traceback.format_exc())
                    return False
                finally:
                    # Thread-safe flag reset
                    with self._rebuild_lock:
                        self.is_rebuilding = False
                    self.logger.debug("Background rebuild finished, is_rebuilding set to False")
            
            # Submit to persistent executor
            future = self._executor.submit(run_sync_rebuild)
            
            # Add completion callback
            def on_complete(fut):
                try:
                    result = fut.result()
                    if result:
                        self.logger.debug("Background rebuild completed successfully")
                    else:
                        self.logger.error("Background rebuild failed")
                except Exception as e:
                    self.logger.error("Background rebuild thread failed: %s", e)
            
            future.add_done_callback(on_complete)
            
            self.logger.debug("Background rebuild scheduled successfully")
            return True
            
        except Exception as e:
            # Reset flag on error
            with self._rebuild_lock:
                self.is_rebuilding = False
            
            self.logger.error("Failed to start background rebuild: %s", e)
            self.logger.error("Traceback: %s", traceback.format_exc())
            return False
    
    def shutdown(self) -> None:
        """
        Shutdown the index service and cleanup resources.
        
        This should be called when the service is no longer needed to ensure
        proper cleanup of the ThreadPoolExecutor.
        """
        if self._executor is not None:
            self.logger.debug("Shutting down ThreadPoolExecutor...")
            self._executor.shutdown(wait=True)  # Wait for current rebuilds to complete
            self._executor = None
            self.logger.debug("ThreadPoolExecutor shutdown completed")
    
    def get_rebuild_status(self) -> dict:
        """
        Get current rebuild status information.
        
        Returns:
            Dictionary with rebuild status
        """
        with self._rebuild_lock:
            is_rebuilding = self.is_rebuilding
        
        return {
            "is_rebuilding": is_rebuilding,
            "index_cache_size": len(self.index_cache.get('files', [])) if self.index_cache else 0
        }
    
    def _search_directory_tree(self, tree: dict, pattern: str, current_path: str) -> list:
        """
        Search files in directory tree using glob pattern.

        Args:
            tree: Directory tree dictionary
            pattern: Glob pattern to match
            current_path: Current path being traversed

        Returns:
            List of matching file paths
        """
        matching_files = []

        for name, subtree in tree.items():
            # Build the full path using forward slashes for consistency
            if current_path:
                full_path = f"{current_path}/{name}"
            else:
                full_path = name

            if subtree is None:
                # This is a file
                # Try matching against full path
                if fnmatch.fnmatch(full_path, pattern):
                    matching_files.append(full_path)
                # Also try matching against just the filename
                elif fnmatch.fnmatch(name, pattern):
                    matching_files.append(full_path)
            else:
                # This is a directory, recurse into it
                matching_files.extend(
                    self._search_directory_tree(subtree, pattern, full_path)
                )

        return matching_files

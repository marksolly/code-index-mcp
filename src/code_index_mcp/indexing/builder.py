"""
Main index builder that coordinates all indexing components.

This module provides the main IndexBuilder class that orchestrates the entire
indexing process, from file scanning to relationship analysis to final index assembly.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..services.database import DatabaseService
from .models import FileInfo, FileAnalysisResult, ValidationResult
from .scanner import ProjectScanner
from .analyzers import LanguageAnalyzerManager
from .relationships import RelationshipTracker


class IndexBuilder:
    """Main builder class that coordinates all indexing components."""

    def __init__(self, db_service: DatabaseService, max_workers: Optional[int] = None):
        """
        Initialize the index builder.

        Args:
            db_service: An instance of the DatabaseService.
            max_workers: Maximum number of worker threads for parallel processing.
        """
        self.db_service = db_service
        self.max_workers = max_workers
        self.analyzer_manager = LanguageAnalyzerManager(max_workers)
        self.relationship_tracker = RelationshipTracker()
        self.project_path = ""  # Initialize project_path

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
            scanner = ProjectScanner(project_path)
            scan_result = scanner.scan_project()

            # Step 2: Read file contents and analyze in parallel
            analysis_results = self._analyze_files(scan_result.file_list)

            # Step 3: Build relationships between code elements
            relationships = self.relationship_tracker.build_relationships(analysis_results)

            # Step 4: Assemble and write index to database
            self._assemble_and_write_index(scan_result, analysis_results, relationships)

            # Step 5: Add timing and metadata (can be stored in a separate table or file if needed)
            end_time = datetime.now()
            analysis_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # TODO: Store metadata in the database
            print(f"Analysis complete in {analysis_time_ms}ms.")
            print(f"Files with errors: {self._collect_files_with_errors(analysis_results)}")
            print(f"Languages analyzed: {self._collect_analyzed_languages(analysis_results)}")

        except (OSError, IOError, ValueError, RuntimeError) as e:
            # Log the error, no fallback index to create
            print(f"Error building index for {project_path}: {e}")

    def _analyze_files(self, file_list: List[FileInfo]) -> List[FileAnalysisResult]:
        """
        Analyze all files in parallel.

        Args:
            file_list: List of FileInfo objects to analyze

        Returns:
            List of FileAnalysisResult objects
        """
        # Read file contents
        files_with_content = []

        for file_info in file_list:
            try:
                content = self._read_file_content(file_info.path)
                if content is not None:
                    files_with_content.append((file_info, content))
            except (OSError, IOError, UnicodeDecodeError, PermissionError) as e:
                # Log error and add empty content for unreadable files
                print(f"Failed to read file {file_info.path}: {str(e)}")
                files_with_content.append((file_info, ""))  # Empty content for error case

        # Analyze files using the analyzer manager
        return self.analyzer_manager.analyze_files(files_with_content)

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

    def _assemble_and_write_index(self, scan_result, analysis_results, relationships):
        """
        Assemble the index data and write it to the SQLite database.
        """
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        try:
            # Get lookup tables for symbol and relationship types
            cursor.execute("SELECT id, name FROM symbol_types")
            symbol_type_map = {name: id for id, name in cursor.fetchall()}

            cursor.execute("SELECT id, name FROM relationship_types")
            relationship_type_map = {name: id for id, name in cursor.fetchall()}

            # Use a transaction for atomicity and disable constraints for performance
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute("PRAGMA ignore_check_constraints = ON;")
            cursor.execute("BEGIN")

            for result in analysis_results:
                file_info = result.file_info
                cursor.execute(
                    """
                    INSERT INTO files (path, size, line_count, modified_time, language)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        file_info.path,
                        file_info.size,
                        self._estimate_line_count(result),
                        file_info.modified_time,
                        file_info.language,
                    ),
                )
                file_id = cursor.lastrowid

                # A map for symbol names to their DB IDs for the current file
                file_symbol_map = {}

                # Insert classes and store their IDs
                for cls in result.classes:
                    cursor.execute(
                        """
                        INSERT INTO code_symbols (file_id, name, type_id, line_start, line_end)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            file_id,
                            cls.name,
                            symbol_type_map['class'],
                            cls.line_start,
                            cls.line_end,
                        ),
                    )
                    class_symbol_id = cursor.lastrowid
                    file_symbol_map[cls.name] = class_symbol_id

                # Insert functions and store their IDs and properties
                for func in result.functions:
                    cursor.execute(
                        """
                        INSERT INTO code_symbols (file_id, name, type_id, line_start, line_end)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            file_id,
                            func.name,
                            symbol_type_map['function'],
                            func.line_start,
                            func.line_end,
                        ),
                    )
                    func_symbol_id = cursor.lastrowid
                    file_symbol_map[func.name] = func_symbol_id

                    # Store parameters in symbol_properties
                    if func.parameters:
                        cursor.execute(
                            """
                            INSERT INTO symbol_properties (symbol_id, key, value)
                            VALUES (?, ?, ?)
                            """,
                            (func_symbol_id, 'parameters', json.dumps(func.parameters)),
                        )

                # Insert imports as symbols and store their properties
                for imp in result.imports:
                    cursor.execute(
                        """
                        INSERT INTO code_symbols (file_id, name, type_id, line_start, line_end)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            file_id,
                            imp.module,  # Using module name as the symbol name
                            symbol_type_map['import'],
                            imp.line_number,
                            imp.line_number,
                        ),
                    )
                    import_symbol_id = cursor.lastrowid

                    # Store imported_names in symbol_properties
                    if imp.imported_names:
                        cursor.execute(
                            """
                            INSERT INTO symbol_properties (symbol_id, key, value)
                            VALUES (?, ?, ?)
                            """,
                            (import_symbol_id, 'imported_names', json.dumps(imp.imported_names)),
                        )

                # Create 'contains_method' relationships
                for cls in result.classes:
                    class_symbol_id = file_symbol_map.get(cls.name)
                    if not class_symbol_id:
                        continue

                    for method_name in cls.methods:
                        method_symbol_id = file_symbol_map.get(method_name)
                        if method_symbol_id:
                            cursor.execute(
                                """
                                INSERT INTO relationships (source_symbol_id, target_symbol_id, type_id)
                                VALUES (?, ?, ?)
                                """,
                                (class_symbol_id, method_symbol_id, relationship_type_map['contains_method']),
                            )

            # TODO: Insert other relationships (calls, inherits, etc.) from the `relationships` object.

            conn.commit()
            
            # Re-enable constraints
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA ignore_check_constraints = OFF;")

        except Exception as e:
            conn.rollback()
            print(f"Database transaction failed: {e}")
        finally:
            cursor.close()

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

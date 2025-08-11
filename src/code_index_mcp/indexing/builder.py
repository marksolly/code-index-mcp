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
from .models import ClassInfo, FileInfo, FileAnalysisResult, ValidationResult
from .scanner import ProjectScanner
from ..analyzers.manager import LanguageAnalyzerManager


class GraphBuilder:
    """Builds the relationship graph from analysis results."""

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        self.symbol_cache = {}

    def build_graph(self, analysis_results: List[FileAnalysisResult]):
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        for result in analysis_results:
            file_id = self._get_or_create_file_symbol(cursor, result.file_info)

            # Create symbols for classes first, so they are available for method qnames
            for a_class in result.classes:
                self._get_or_create_symbol(
                    cursor, file_id, a_class, "class", file_info=result.file_info
                )

            # Create symbols for functions, determining qname based on class scope
            for function in result.functions:
                source_id = self._get_or_create_symbol(
                    cursor,
                    file_id,
                    function,
                    "function",
                    file_info=result.file_info,
                    classes=result.classes,
                )
                for call in function.calls:
                    target_ids = self._find_symbol(cursor, call)
                    if target_ids:
                        confidence = 1.0 / len(target_ids)
                        for target_id in target_ids:
                            self._create_relationship(
                                cursor, source_id, target_id, "calls", confidence
                            )

        conn.commit()

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

    def _generate_qname(
        self,
        symbol_info: Any,
        symbol_type: str,
        file_info: FileInfo,
        classes: Optional[List[ClassInfo]] = None,
    ) -> str:
        """Generates a qualified name (qname) for a symbol."""
        if symbol_type == "function":
            if classes:
                for a_class in classes:
                    # This assumes method names are stored in `a_class.methods`
                    if hasattr(a_class, "methods") and any(
                        m.name == symbol_info.name for m in a_class.methods
                    ):
                        # Primary Rule: Enclosing scope (e.g., `User.save`)
                        return f"{a_class.name}.{symbol_info.name}"
            # Fallback Rule: File name (e.g., `audit.py:log_event`)
            return f"{Path(file_info.path).name}:{symbol_info.name}"

        if symbol_type == "class":
            # Fallback Rule for top-level symbols
            return f"{Path(file_info.path).name}:{symbol_info.name}"

        # Default for other types (e.g., imports, variables)
        return symbol_info.name

    def _get_or_create_symbol(
        self,
        cursor,
        file_id: int,
        symbol_info: Any,
        symbol_type: str,
        file_info: FileInfo,
        classes: Optional[List[ClassInfo]] = None,
    ) -> int:
        qname = self._generate_qname(symbol_info, symbol_type, file_info, classes)

        if (file_id, qname) in self.symbol_cache:
            return self.symbol_cache[(file_id, qname)]

        cursor.execute(
            "SELECT id FROM code_symbols WHERE file_id = ? AND name = ?", (file_id, qname)
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
            INSERT INTO code_symbols (file_id, name, type_id, line_start, line_end)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                file_id,
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
        # This is a simplification. It will be improved to handle qnames and ambiguity.
        cursor.execute("SELECT id FROM code_symbols WHERE name LIKE ?", (f"%:{symbol_name}",))
        rows = cursor.fetchall()
        return [row[0] for row in rows]

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

    def __init__(self, db_service: DatabaseService, max_workers: Optional[int] = None):
        """
        Initialize the index builder.

        Args:
            db_service: An instance of the DatabaseService.
            max_workers: Maximum number of worker threads for parallel processing.
        """
        self.db_service = db_service
        self.max_workers = max_workers
        self.analyzer_manager = LanguageAnalyzerManager()
        self.graph_builder = GraphBuilder(db_service)
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
            self.graph_builder.build_graph(analysis_results)

            # Step 4: Assemble and write index to database
            # self._assemble_and_write_index(scan_result, analysis_results, {})

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

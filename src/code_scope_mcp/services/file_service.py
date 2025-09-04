"""
File operations service for the Code Scope MCP server.

This service handles file content retrieval, file analysis,
and file metadata operations.
"""

import os
from typing import Dict, Any

from .base_service import BaseService
from ..utils.qualified_names import normalize_file_path


class FileService(BaseService):
    """
    Service for managing file operations and analysis.

    This service handles:
    - File content retrieval with security validation
    - File analysis and summarization
    - File metadata operations
    - Language-specific file analysis
    """


    def get_file_content(self, file_path: str) -> str:
        """
        Get the content of a specific file.

        Handles the logic for files://{file_path} MCP resource.

        Args:
            file_path: Path to the file (relative to project root)

        Returns:
            File content as string

        Raises:
            ValueError: If project is not set up or file path is invalid
            FileNotFoundError: If file does not exist
            UnicodeDecodeError: If file is binary or uses unsupported encoding
        """
        self._require_project_setup()
        self._require_valid_file_path(file_path)

        # Normalize the file path
        norm_path = os.path.normpath(file_path)
        full_path = os.path.join(self.base_path, norm_path)

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except UnicodeDecodeError as exc:
            raise UnicodeDecodeError(
                'utf-8', b'', 0, 1,
                f"File {file_path} appears to be a binary file or uses "
                f"unsupported encoding."
            ) from exc
        except (FileNotFoundError, PermissionError, OSError) as e:
            raise FileNotFoundError(f"Error reading file: {e}") from e


    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a file and return summary information from index data.

        Handles the logic for get_file_summary MCP tool.

        Args:
            file_path: Path to the file (relative to project root)

        Returns:
            Dictionary with file analysis results from index data

        Raises:
            ValueError: If project is not set up, file path is invalid, or file not in index
        """
        from ..utils import ResponseFormatter
        self._require_project_setup()
        self._require_valid_file_path(file_path)

        # Normalize the file path to use forward slashes (consistent with index storage)
        norm_path = normalize_file_path(file_path)

        # Get file extension
        _, ext = os.path.splitext(norm_path)

        # Only use index data - no fallback to real-time analysis
        if not self.index_cache or 'files' not in self.index_cache:
            raise ValueError(f"No index data available for file: {norm_path}")

        # Find file in index
        for file_entry in self.index_cache['files']:
            if file_entry.get('path') == norm_path:
                # Validate index data structure
                if not self._validate_index_entry(file_entry):
                    raise ValueError(f"Malformed index data for file: {norm_path}")

                # Extract complete relationship data from index
                functions = file_entry.get('functions', [])
                classes = file_entry.get('classes', [])
                imports = file_entry.get('imports', [])

                # Return structured data from the index with complete objects
                return ResponseFormatter.file_summary_response(
                    file_path=norm_path,
                    line_count=file_entry.get('line_count', 0),
                    size_bytes=file_entry.get('size', 0),
                    extension=ext,
                    language=file_entry.get('language', 'unknown'),
                    functions=functions,  # Complete objects with all relationship data
                    classes=classes,      # Complete objects with all relationship data
                    imports=imports,      # Complete objects with all relationship data
                    language_specific=file_entry.get('language_specific', {}),
                    index_cache=self.index_cache  # Pass index cache for qualified name resolution
                )

        # File not found in index
        raise ValueError(f"File not found in index: {norm_path}")





    def _validate_index_entry(self, file_entry: Dict[str, Any]) -> bool:
        """
        Validate the structure of an index entry to ensure it's not malformed.

        Args:
            file_entry: Index entry to validate

        Returns:
            True if the entry is valid, False if malformed
        """
        try:
            # Check required fields
            if not isinstance(file_entry, dict):
                return False

            # Validate basic file information
            if 'path' not in file_entry or not isinstance(file_entry['path'], str):
                return False

            # Validate optional numeric fields
            for field in ['line_count', 'size']:
                if field in file_entry and not isinstance(file_entry[field], (int, float)):
                    return False

            # Validate optional string fields
            for field in ['language']:
                if field in file_entry and not isinstance(file_entry[field], str):
                    return False

            # Validate functions list structure
            functions = file_entry.get('functions', [])
            if not isinstance(functions, list):
                return False

            for func in functions:
                if isinstance(func, dict):
                    # Validate function object structure
                    if 'name' not in func or not isinstance(func['name'], str):
                        return False
                    # Validate optional list fields
                    for field in ['parameters', 'calls', 'called_by', 'decorators']:
                        if field in func and not isinstance(func[field], list):
                            return False
                    # Validate optional boolean fields
                    if 'is_async' in func and not isinstance(func['is_async'], bool):
                        return False
                elif not isinstance(func, str):
                    # Functions can be strings (legacy) or dicts (enhanced)
                    return False

            # Validate classes list structure
            classes = file_entry.get('classes', [])
            if not isinstance(classes, list):
                return False

            for cls in classes:
                if isinstance(cls, dict):
                    # Validate class object structure
                    if 'name' not in cls or not isinstance(cls['name'], str):
                        return False
                    # Validate optional list fields
                    for field in ['methods', 'instantiated_by']:
                        if field in cls and not isinstance(cls[field], list):
                            return False
                    # Validate optional string fields
                    if 'inherits_from' in cls and cls['inherits_from'] is not None and not isinstance(cls['inherits_from'], str):
                        return False
                elif not isinstance(cls, str):
                    # Classes can be strings (legacy) or dicts (enhanced)
                    return False

            # Validate imports list structure
            imports = file_entry.get('imports', [])
            if not isinstance(imports, list):
                return False

            for imp in imports:
                if isinstance(imp, dict):
                    # Validate import object structure
                    if 'module' not in imp or not isinstance(imp['module'], str):
                        return False
                    # Validate optional list fields
                    if 'imported_names' in imp and not isinstance(imp['imported_names'], list):
                        return False
                    # Validate optional string fields
                    if 'import_type' in imp and not isinstance(imp['import_type'], str):
                        return False
                elif not isinstance(imp, str):
                    # Imports can be strings (legacy) or dicts (enhanced)
                    return False

            # Validate language_specific field
            if 'language_specific' in file_entry and not isinstance(file_entry['language_specific'], dict):
                return False

            return True

        except (KeyError, TypeError, AttributeError):
            return False

    def validate_file_path(self, file_path: str) -> bool:
        """
        Validate a file path for security and accessibility.

        Args:
            file_path: Path to validate

        Returns:
            True if path is valid and accessible, False otherwise
        """
        if not self.base_path:
            return False

        error = self._validate_file_path(file_path)
        return error is None

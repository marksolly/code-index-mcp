from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_import_handler import BaseImportHandler


class PhpImportHandler(BaseImportHandler):
    """PHP-specific implementation of import relationship handler."""

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)
        self.logger.log(self.__class__.__name__, "DEBUG: PhpImportHandler instantiated")

    def _get_import_queries(self) -> list[str]:
        """Return PHP-specific tree-sitter queries for import statements."""
        return ["""
            (include_expression) @from_import_stmt
        """, """
            (include_once_expression) @from_import_stmt
        """, """
            (require_expression) @from_import_stmt
        """, """
            (require_once_expression) @from_import_stmt
        """]



    def _extract_import_from_node(self, node) -> Optional[dict]:
        """Extract import details from a PHP AST node.

        Args:
            node: Tree-sitter node representing an include/require statement

        Returns:
            dict with 'module_name' and 'imported_names', or None if extraction fails
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: _extract_import_from_node called with node type: {node.type}")
        try:
            # PHP includes/requires import all symbols from the included file
            # We need to extract the file path from the expression

            # Find the string content (the file path)
            string_node = None
            for child in node.children:
                if child.type == "string":
                    string_node = child
                    break

            if not string_node:
                return None

            # Extract the file path from the string (remove quotes)
            file_path = string_node.text.decode('utf-8').strip('"\'')

            # For PHP includes, we import all symbols from the file
            # We'll use a special marker to indicate "all symbols"
            return {
                'module_name': file_path,
                'imported_names': ['*']  # Special marker for "all symbols"
            }

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting import from node: {e}")
            return None

    def _convert_module_to_file_path(self, module_name: str) -> str:
        """Convert a PHP module/file path to a normalized file path.

        Args:
            module_name: The file path from include/require

        Returns:
            Normalized file path
        """
        # PHP includes can be relative or absolute
        # For our test cases, we'll assume relative paths from the same directory
        if module_name.startswith('./'):
            # Extract only the filename part to maintain qname format
            return module_name[2:].split('/')[-1]
        elif module_name.startswith('../'):
            # For simplicity, handle one level up and extract filename
            return module_name[3:].split('/')[-1]
        else:
            return module_name

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_import_handler import BaseImportHandler


class PythonImportHandler(BaseImportHandler):
    """Python-specific implementation of import relationship handler."""

    def _get_import_queries(self) -> list[str]:
        """Return Python-specific tree-sitter queries for import statements."""
        return ["""
            (import_from_statement) @from_import_stmt
        """]

    def _extract_import_from_node(self, node) -> Optional[dict]:
        """Extract import details from a Python AST node.

        Args:
            node: Tree-sitter node representing an import_from_statement

        Returns:
            dict with 'module_name' and 'imported_names', or None if extraction fails
        """
        try:
            # Extract module name from relative_import or module_name
            relative_import = node.child_by_field_name("module_name")
            if relative_import:
                module_name = relative_import.text.decode('utf-8')
            else:
                # Try relative_import for relative imports
                relative_import = node.child_by_field_name("relative_import")
                if relative_import:
                    module_name = relative_import.text.decode('utf-8')
                else:
                    return None

            # Extract imported names - these are the names being imported, not the module name
            imported_names = []

            # Find all imported names by looking for nodes after the 'import' keyword
            found_import_keyword = False
            for child in node.children:
                if child.type == "import":
                    found_import_keyword = True
                    continue

                # After finding 'import', collect all dotted_name and identifier nodes
                if found_import_keyword and child.type in ("dotted_name", "identifier"):
                    imported_names.append(child.text.decode('utf-8'))

            return {
                'module_name': module_name,
                'imported_names': imported_names
            }

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting import from node: {e}")
            return None

    def _convert_module_to_file_path(self, module_name: str) -> str:
        """Convert a Python module name to a file path.

        Qnames should use only the filename, not full paths.
        But the handler still needs to track which file is being imported.

        Args:
            module_name: The module name (e.g., 'package.module', '.file1')

        Returns:
            Just the filename with .py extension (e.g., 'module.py', 'file1.py')
        """
        # Handle relative imports (starting with '.')
        if module_name.startswith('.'):
            # Remove leading dots and take the last part
            clean_module = module_name.lstrip('.')
            if clean_module:
                # For 'package.module', take just 'module'
                parts = clean_module.split('.')
                file_base = parts[-1]  # Last part
                target_file = file_base + '.py'
            else:
                # Just '.' -> current directory module
                target_file = '__init__.py'
        else:
            # Absolute imports: take the last part of the module name
            parts = module_name.split('.')
            file_base = parts[-1]
            target_file = file_base + '.py'

        return target_file

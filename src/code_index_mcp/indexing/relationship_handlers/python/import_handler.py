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

        Args:
            module_name: The module name (e.g., 'package.module')

        Returns:
            File path string (e.g., 'package/module.py')
        """
        # Convert module name to file path (simplified for test cases)
        if module_name.startswith('.'):
            # Relative import - convert to file path
            target_file = module_name.replace('.', '/') + '.py'
            if target_file.startswith('/'):
                target_file = target_file[1:]
        else:
            target_file = module_name.replace('.', '/') + '.py'

        return target_file

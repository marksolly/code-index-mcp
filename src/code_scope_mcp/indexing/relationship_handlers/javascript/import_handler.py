from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_import_handler import BaseImportHandler


class JavascriptImportHandler(BaseImportHandler):
    """JavaScript-specific implementation of import relationship handler."""

    def _get_import_queries(self) -> list[str]:
        """Return JavaScript-specific tree-sitter queries for import statements."""
        return ["""
            (import_statement) @from_import_stmt
        """]

    def _extract_import_from_node(self, node) -> Optional[dict]:
        """Extract import details from a JavaScript AST node.

        Args:
            node: Tree-sitter node representing an import_statement

        Returns:
            dict with 'module_name' and 'imported_names', or None if extraction fails
        """
        try:
            # Extract module name from the string node
            module_name = None
            for child in node.children:
                if child.type == "string":
                    # Remove quotes around the string
                    module_name = child.text.decode('utf-8').strip('"\'')

            if not module_name:
                return None

            # Extract imported names from import_clause
            imported_names = []
            for child in node.children:
                if child.type == "import_clause":
                    # Find all identifier nodes within the import_clause
                    def find_identifiers_in_clause(node):
                        results = []
                        if node.type == "identifier":
                            results.append(node.text.decode('utf-8'))
                        elif hasattr(node, 'children'):
                            for c in node.children:
                                results.extend(find_identifiers_in_clause(c))
                        return results

                    imported_names = find_identifiers_in_clause(child)

            # Successfully extracted import details - no debug logging needed for production

            return {
                'module_name': module_name,
                'imported_names': imported_names
            }

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting import from node: {e}")
            return None

    def _convert_module_to_file_path(self, module_name: str) -> str:
        """Convert a JavaScript module name to a file path.

        Args:
            module_name: The module name (e.g., './file1.js', 'package/module')

        Returns:
            File path string
        """
        # Handle relative imports
        if module_name.startswith('./') or module_name.startswith('../'):
            # Remove leading ./ and add .js extension if not present
            target_file = module_name
            if target_file.startswith('./'):
                target_file = target_file[2:]
            # Extract only the filename part to maintain qname format
            target_file = target_file.split('/')[-1]
            if not target_file.endswith('.js'):
                target_file += '.js'
            return target_file
        else:
            # For absolute imports, assume they're in node_modules or similar
            # This is a simplified approach for the test cases
            return module_name

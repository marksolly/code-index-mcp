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
            # Debug: Log all fields available on the import_statement node
            self.logger.log(self.__class__.__name__, f"DEBUG: Import statement node type: {node.type}")
            self.logger.log(self.__class__.__name__, f"DEBUG: Import statement children: {[(c.type, c.text.decode('utf-8') if c.text else 'no text') for c in node.children]}")

            # Extract source (module name) from the import statement
            source_node = node.child_by_field_name("source")
            if not source_node:
                return None

            module_name = source_node.text.decode('utf-8').strip('"\'')

            # Extract imported names from import clause
            imported_names = []
            import_clause = None

            # Find import_clause by iterating through children (not by field name)
            for child in node.children:
                if child.type == "import_clause":
                    import_clause = child
                    break

            self.logger.log(self.__class__.__name__, f"DEBUG: Import clause found: {import_clause is not None}")
            if import_clause:
                # Debug: Log the structure of the import clause
                self.logger.log(self.__class__.__name__, f"DEBUG: Import clause type: {import_clause.type}")
                self.logger.log(self.__class__.__name__, f"DEBUG: Import clause children: {[(c.type, c.text.decode('utf-8') if c.text else 'no text') for c in import_clause.children]}")

                # Handle different types of import clauses
                for child in import_clause.children:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Processing child type: {child.type}")
                    if child.type == "identifier":
                        # import { foo } from 'module' -> foo
                        imported_names.append(child.text.decode('utf-8'))
                    elif child.type == "named_imports":
                        # import { foo, bar } from 'module' -> foo, bar
                        # named_imports contains import_specifier children
                        self.logger.log(self.__class__.__name__, f"DEBUG: Named imports children: {[(c.type, c.text.decode('utf-8') if c.text else 'no text') for c in child.children]}")
                        for named_import in child.children:
                            if named_import.type == "import_specifier":
                                name_node = named_import.child_by_field_name("name")
                                if name_node:
                                    imported_names.append(name_node.text.decode('utf-8'))
                            elif named_import.type == "identifier":
                                # Sometimes the import_specifier is just an identifier
                                imported_names.append(named_import.text.decode('utf-8'))
                    elif child.type == "namespace_import":
                        # import * as foo from 'module' -> foo
                        alias_node = child.child_by_field_name("alias")
                        if alias_node:
                            imported_names.append(alias_node.text.decode('utf-8'))
                    elif child.type == "import_specifier":
                        # Direct import_specifier (fallback)
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            imported_names.append(name_node.text.decode('utf-8'))

            self.logger.log(self.__class__.__name__, f"DEBUG: Extracted import: {module_name} -> {imported_names}")

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
            if not target_file.endswith('.js'):
                target_file += '.js'
            return target_file
        else:
            # For absolute imports, assume they're in node_modules or similar
            # This is a simplified approach for the test cases
            return module_name

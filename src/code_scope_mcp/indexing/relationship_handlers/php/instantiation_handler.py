from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_instantiation_handler import BaseInstantiationHandler


class PhpInstantiationHandler(BaseInstantiationHandler):
    """PHP-specific implementation of instantiation relationship handler."""

    def _get_instantiation_queries(self) -> list[str]:
        """Return PHP-specific tree-sitter queries for finding instantiations."""
        return [
            # Query for new expressions - match object_creation_expression and capture class name
            """
            (object_creation_expression
              [
                (qualified_name (name) @name)
                (variable_name (name) @name)
                (name) @name
              ]
            ) @instantiation
            """
        ]

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved instantiation relationships from AST.
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: extract_from_ast called for {file_qname}")
        super().extract_from_ast(tree, writer, reader, file_qname)
        self.logger.log(self.__class__.__name__, f"DEBUG: extract_from_ast completed for {file_qname}")

    def _extract_instantiation_from_node(self, node) -> Optional[dict]:
        """Extract instantiation details from a PHP AST node.

        Args:
            node: Tree-sitter node representing an object_creation_expression

        Returns:
            dict with 'class_name' key, or None if extraction fails
        """
        try:
            # Find the class name in the object creation expression
            # PHP uses either 'qualified_name' or 'name' for class names
            class_name_node = None

            # Look for qualified_name first (Namespace\ClassName)
            for child in node.children:
                if child.type == "qualified_name":
                    class_name_node = child
                    break
                elif child.type == "name":
                    class_name_node = child
                    break

            if not class_name_node:
                return None

            # Extract the class name
            class_name = class_name_node.text.decode('utf-8')

            return {'class_name': class_name}

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting instantiation from node: {e}")
            return None

    def _find_containing_context(self, node, file_qname: str) -> Optional[str]:
        """Find the containing context (function/method) for an instantiation.

        Args:
            node: Tree-sitter node representing the instantiation
            file_qname: The file qualified name

        Returns:
            The qname of the containing function/method, or the file qname if at global level.
            Returns None if context cannot be determined.
        """
        try:
            current = node.parent
            while current:
                if current.type == "method_declaration":
                    # Get method name
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        method_name = name_node.text.decode('utf-8')

                        # Find the containing class
                        class_name = None
                        parent = current.parent
                        while parent:
                            if parent.type == "class_declaration":
                                class_name_node = parent.child_by_field_name("name")
                                if class_name_node:
                                    class_name = class_name_node.text.decode('utf-8')
                                break
                            parent = parent.parent

                        if class_name:
                            return f"{class_name}.{method_name}"
                        else:
                            # Extract clean filename from file_qname (remove :__FILE__ suffix if present)
                            clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                            return f"{clean_file_name}:{method_name}"

                elif current.type == "function_definition":
                    # Get function name
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        function_name = name_node.text.decode('utf-8')

                        # Extract clean filename from file_qname (remove :__FILE__ suffix if present)
                        clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                        return f"{clean_file_name}:{function_name}"

                current = current.parent

            # If no containing function/method found, return file qname
            return file_qname

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error finding containing context: {e}")
            return file_qname

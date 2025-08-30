from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_instantiation_handler import BaseInstantiationHandler


class PythonInstantiationHandler(BaseInstantiationHandler):
    """Python-specific implementation of instantiation relationship handler."""

    def _get_instantiation_queries(self) -> list[str]:
        """Return Python-specific tree-sitter queries for finding instantiations."""
        return [
            # Query for direct class instantiations (MyClass())
            """
            (call
              function: (identifier) @class_name
            ) @instantiation
            """,
            # Query for attribute access instantiations (module.Class())
            """
            (call
              function: (attribute
                object: (identifier) @module
                attribute: (identifier) @class_name
              )
            ) @instantiation
            """
        ]

    def _extract_instantiation_from_node(self, node) -> Optional[dict]:
        """Extract instantiation details from a Python AST node.

        Args:
            node: Tree-sitter node representing a call expression

        Returns:
            dict with 'class_name' key, or None if extraction fails
        """
        try:
            # Get the function node
            function_node = node.child_by_field_name("function")
            if not function_node:
                return None

            if function_node.type == "identifier":
                # Direct class instantiation (MyClass())
                class_name = function_node.text.decode('utf-8')
                return {'class_name': class_name}

            elif function_node.type == "attribute":
                # Attribute access instantiation (module.Class())
                # Extract module and class from attribute
                object_node = function_node.child_by_field_name("object")
                attribute_node = function_node.child_by_field_name("attribute")

                if object_node and attribute_node:
                    module_name = object_node.text.decode('utf-8')
                    class_name = attribute_node.text.decode('utf-8')

                    # For now, we just use the class name for resolution
                    # The full qualified name could be used for more precise matching
                    return {'class_name': class_name}

            return None

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting instantiation from node: {e}")
            return None

    def _find_containing_context(self, node, file_qname: str) -> Optional[str]:
        """Find the containing context (function/method) for an instantiation.

        Args:
            node: Tree-sitter node representing the instantiation
            file_qname: The file qualified name

        Returns:
            The qname of the containing function/method, or the file qname if at module level.
            Returns None if context cannot be determined.
        """
        try:
            current = node.parent
            while current:
                if current.type == "function_definition":
                    # Get function name
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        function_name = name_node.text.decode('utf-8')

                        # Check if this is a method (inside a class) or module function
                        class_name = None
                        parent = current.parent
                        while parent:
                            if parent.type == "class_definition":
                                class_name_node = parent.child_by_field_name("name")
                                if class_name_node:
                                    class_name = class_name_node.text.decode('utf-8')
                                break
                            parent = parent.parent

                        if class_name:
                            return f"{class_name}.{function_name}"
                        else:
                            # Extract clean filename from file_qname (remove :__FILE__ suffix if present)
                            clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                            return f"{clean_file_name}:{function_name}"

                current = current.parent

            # If no containing function found, return file qname
            return file_qname

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error finding containing context: {e}")
            return file_qname

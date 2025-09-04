from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..common.base_file_function_call_handler import BaseFileFunctionCallHandler


class PhpFileFunctionCallHandler(BaseFileFunctionCallHandler):
    """PHP-specific implementation of file function call relationship handler."""

    def _get_function_call_queries(self) -> list[str]:
        """Return PHP-specific tree-sitter queries for finding function calls."""
        return [
            # Query for function call expressions
            """
            (function_call_expression
              function: (name) @function_name
            ) @call
            """
        ]

    def _extract_function_from_node(self, node, function_name: str) -> Optional[dict]:
        """Extract function call details from an AST node.

        Args:
            node: Tree-sitter node representing the function_call_expression
            function_name: The function name as a string

        Returns:
            dict with keys:
            - 'function_name': str - the name of the function being called
            - 'source_qname': str - the qualified name of the calling method/class.method
            Returns None if extraction fails.
        """
        try:
            # Find containing context (class and method names)
            class_name, calling_method_name = self._find_calling_context(node)

            # Construct source_qname
            if class_name and calling_method_name:
                source_qname = f"{class_name}.{calling_method_name}"
            elif calling_method_name:
                # This shouldn't happen for file functions, but handle it anyway
                source_qname = calling_method_name
            else:
                return None

            result = {
                'function_name': function_name,
                'source_qname': source_qname
            }
            return result

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting function from node: {e}")
            return None

    def _find_calling_context(self, call_node):
        """Find the class and method context where this call occurs."""
        class_name = None
        calling_method_name = None

        current = call_node.parent
        while current:
            if current.type == "method_declaration":
                # Found the calling method
                name_node = current.child_by_field_name("name")
                if name_node:
                    calling_method_name = name_node.text.decode('utf-8')

                # Find the containing class
                parent = current.parent
                while parent:
                    if parent.type == "class_declaration":
                        class_name_node = parent.child_by_field_name("name")
                        if class_name_node:
                            class_name = class_name_node.text.decode('utf-8')
                        break
                    parent = parent.parent
                break

            elif current.type == "function_definition":
                # Found a standalone function
                name_node = current.child_by_field_name("name")
                if name_node:
                    calling_method_name = name_node.text.decode('utf-8')
                break

            current = current.parent

        return class_name, calling_method_name

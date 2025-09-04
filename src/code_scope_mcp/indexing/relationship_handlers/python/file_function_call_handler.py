from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_file_function_call_handler import BaseFileFunctionCallHandler


class PythonFileFunctionCallHandler(BaseFileFunctionCallHandler):
    """Python-specific implementation of file function call relationship handler."""

    def _get_function_call_queries(self) -> list[str]:
        """Return Python-specific tree-sitter queries for finding standalone function calls."""
        return [
            # Query for standalone function calls (not attribute access)
            # This captures: helper_function() but not self.helper_function() or obj.helper_function()
            """
            (call
              function: (identifier) @function_name
            ) @call
            """
        ]

    def _extract_function_from_node(self, node, function_name: str) -> Optional[dict]:
        """Extract function call details from a Python AST node.

        Args:
            node: Tree-sitter node representing a call expression
            function_name: The function name extracted from the query

        Returns:
            dict with 'function_name' and 'source_qname', or None if extraction fails
        """
        try:
            # Find the containing class and method
            class_name = None
            calling_method_name = None
            current = node.parent
            while current:
                if current.type == "function_definition":
                    # Get method name
                    for child in current.children:
                        if child.type == "identifier":
                            calling_method_name = child.text.decode('utf-8')
                            break
                elif current.type == "class_definition":
                    # Get class name
                    for child in current.children:
                        if child.type == "identifier":
                            class_name = child.text.decode('utf-8')
                            break
                    break
                current = current.parent

            if class_name and calling_method_name:
                source_qname = f"{class_name}.{calling_method_name}"
                return {
                    'function_name': function_name,
                    'source_qname': source_qname
                }
            else:
                # If we can't find a proper class.method context, return None
                # This ensures we only process calls that are actually within methods
                return None

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting function call from node: {e}")
            return None

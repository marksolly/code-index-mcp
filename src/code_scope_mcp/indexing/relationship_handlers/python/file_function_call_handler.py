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

    def _extract_function_from_node(self, node, function_name: str, file_qname: str) -> Optional[dict]:
        """Extract function call details from a Python AST node.

        Args:
            node: Tree-sitter node representing a call expression
            function_name: The function name extracted from the query
            file_qname: The file qualified name (e.g., 'file3.py')

        Returns:
            dict with 'function_name' and 'source_qname', or None if extraction fails
        """
        try:
            # Strip :__FILE__ suffix if present for constructing proper qnames
            base_file_qname = file_qname
            if base_file_qname.endswith(":__FILE__"):
                base_file_qname = base_file_qname[:-9]  # Remove ":__FILE__"

            # Find the containing class and method or module-level function
            class_name = None
            containing_function_name = None
            current = node.parent
            while current:
                if current.type == "function_definition" and containing_function_name is None:
                    # Get function name
                    for child in current.children:
                        if child.type == "identifier":
                            containing_function_name = child.text.decode('utf-8')
                            break
                elif current.type == "class_definition":
                    # Get class name
                    for child in current.children:
                        if child.type == "identifier":
                            class_name = child.text.decode('utf-8')
                            break
                current = current.parent

            if class_name:
                # We're in a class, check if it's a method call
                if containing_function_name:
                    source_qname = f"{class_name}.{containing_function_name}"
                else:
                    # Call in class but not in a method, skip
                    return None
            elif containing_function_name:
                # Call from within a module-level function
                source_qname = f"{base_file_qname}:{containing_function_name}"
            else:
                # If we can't find either class.method or module function context, return None
                return None

            return {
                'function_name': function_name,
                'source_qname': source_qname
            }

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting function call from node: {e}")
            return None

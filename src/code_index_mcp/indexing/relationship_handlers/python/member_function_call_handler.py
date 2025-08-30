from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_member_function_call_handler import BaseMemberFunctionCallHandler


class PythonMemberFunctionCallHandler(BaseMemberFunctionCallHandler):
    """Python-specific implementation of member function call relationship handler."""

    def _get_member_call_queries(self) -> list[str]:
        """Return Python-specific tree-sitter queries for finding member function calls."""
        return [
            # Query for call where function is attribute access (member calls)
            # This captures: self.start(), self.engine.start_engine(), obj.method()
            """
            (call
              function: (attribute) @function_attr
            ) @call
            """
        ]

    def _extract_member_call_from_node(self, call_node, function_attr_node) -> Optional[dict]:
        """Extract member function call details from Python AST nodes.

        Args:
            call_node: Tree-sitter node representing a call expression
            function_attr_node: Tree-sitter node representing the attribute access

        Returns:
            dict with 'method_name', 'object_name', 'class_name', and 'calling_method_name', or None if extraction fails
        """
        try:
            # Extract the method name (the final attribute in the chain)
            method_name = None
            if function_attr_node.type == "attribute":
                # Get the final attribute name
                current = function_attr_node
                while current.type == "attribute":
                    if current.child_by_field_name("attribute"):
                        current = current.child_by_field_name("attribute")
                    else:
                        break
                if current.type == "identifier":
                    method_name = current.text.decode('utf-8')

            # Extract the full object path by getting the text of the object part
            object_name = None
            if function_attr_node.type == "attribute":
                obj = function_attr_node.child_by_field_name("object")
                if obj:
                    # Get the full text of the object (handles nested attributes automatically)
                    object_name = obj.text.decode('utf-8')

            if not method_name or not object_name:
                return None

            # Find the containing class and method
            class_name = None
            calling_method_name = None
            current = call_node.parent
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

            return {
                'method_name': method_name,
                'object_name': object_name,
                'class_name': class_name,
                'calling_method_name': calling_method_name
            }

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting member call from node: {e}")
            return None

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_file_function_call_handler import BaseFileFunctionCallHandler


class CFileFunctionCallHandler(BaseFileFunctionCallHandler):
    """C-specific implementation of file function call relationship handler."""

    def _get_function_call_queries(self) -> list[str]:
        """Return C-specific tree-sitter queries for function calls."""
        return ["""
            (call_expression
                function: (identifier) @function_name) @call
        """]

    def _extract_function_from_node(self, node, function_name: str, file_qname: str) -> Optional[dict]:
        """Extract function call details from a C function call AST node.

        Args:
            node: Tree-sitter node representing a call_expression
            function_name: The function name being called
            file_qname: The file qualified name

        Returns:
            dict with function details, or None if extraction fails
        """
        try:
            # For C, we need to identify which function context contains this call
            # Walk up the AST to find the containing function
            source_qname = file_qname  # Default fallback

            # Traverse up the AST to find containing function
            current_node = node.parent
            while current_node:
                if current_node.type == "function_definition":
                    # Extract function name from the function definition
                    function_name_node = current_node.child_by_field_name("declarator")
                    if function_name_node:
                        if function_name_node.type == "identifier":
                            func_name = function_name_node.text.decode('utf-8')
                        elif function_name_node.type == "function_declarator":
                            func_declarator = function_name_node.child_by_field_name("declarator")
                            if func_declarator and func_declarator.type == "identifier":
                                func_name = func_declarator.text.decode('utf-8')
                            else:
                                break
                        else:
                            break

                        # file_qname might be like "main.c:__FILE__", extract just the filename
                        file_name = file_qname.split(':')[0] if ':' in file_qname else file_qname
                        source_qname = f"{file_name}:{func_name}"
                        break
                current_node = current_node.parent

            return {
                'function_name': function_name,
                'source_qname': source_qname
            }

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting function from node: {e}")
            return None

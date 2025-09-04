from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_file_function_call_handler import BaseFileFunctionCallHandler


class JavascriptFileFunctionCallHandler(BaseFileFunctionCallHandler):
    """JavaScript-specific implementation of file function call relationship handler."""

    def _get_function_call_queries(self) -> list[str]:
        """Return JavaScript-specific tree-sitter queries for finding standalone function calls."""
        return ["""
            (call_expression
                function: (identifier) @function_name
            ) @call
        """]

    def _extract_function_from_node(self, node, function_name: str) -> Optional[dict]:
        """Extract function call details from a JavaScript AST node.

        Args:
            node: Tree-sitter node representing a call_expression
            function_name: The function name extracted from the query

        Returns:
            dict with 'function_name' and 'source_qname', or None if extraction fails
        """
        try:
            # Debug: Log node structure
            self.logger.log(self.__class__.__name__, f"DEBUG: Call expression node type: {node.type}")
            self.logger.log(self.__class__.__name__, f"DEBUG: Function name: {function_name}")

            # Find the containing context (function/method/class)
            source_qname = self._find_containing_context_for_call(node)

            if source_qname:
                self.logger.log(self.__class__.__name__, f"DEBUG: Extracted function call: {function_name} from {source_qname}")
                return {
                    'function_name': function_name,
                    'source_qname': source_qname
                }
            else:
                self.logger.log(self.__class__.__name__, "DEBUG: Could not determine containing context")
                return None

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting function call from node: {e}")
            return None

    def _find_containing_context_for_call(self, node) -> Optional[str]:
        """Find the containing context (function/method) for a function call.

        Args:
            node: The call expression node

        Returns:
            The qname of the containing function/method, or None if at module level
        """
        try:
            # Walk up the AST to find containing function/method/class
            current = node.parent
            class_context = None
            method_context = None

            while current:
                if current.type == "method_definition":
                    # Found a method context
                    method_name = self._extract_context_name(current)
                    if method_name:
                        method_context = method_name
                    # Continue walking up to find class context
                elif current.type == "class_declaration":
                    # Found a class context
                    class_name = self._extract_class_name(current)
                    if class_name:
                        class_context = class_name
                    # Continue walking up to see if there are more contexts
                elif current.type in ["function_declaration", "function_expression", "arrow_function"]:
                    # Found a function context (not in a class)
                    function_name = self._extract_context_name(current)
                    if function_name:
                        # For standalone functions, we need to construct the proper qname
                        # Since we don't have access to the actual file path in this context,
                        # we'll return a format that can be resolved later
                        return f"function:{function_name}"
                    break
                elif current.type == "program":
                    # At module level
                    break

                current = current.parent

            # Construct the appropriate qname based on what we found
            if class_context and method_context:
                # We're in a class method
                return f"{class_context}.{method_context}"
            elif class_context:
                # We're in a class but no specific method found
                return f"{class_context}.method"
            elif method_context:
                # We're in a standalone function
                return f"function:{method_context}"
            else:
                # At module level or couldn't determine context
                return None

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error finding containing context: {e}")
            return None

    def _extract_context_name(self, function_node) -> Optional[str]:
        """Extract function/method name from function node."""
        try:
            if function_node.type == "function_declaration":
                # function name() { ... }
                name_node = function_node.child_by_field_name("name")
                if name_node:
                    return name_node.text.decode('utf-8')
            elif function_node.type == "method_definition":
                # class methods
                name_node = function_node.child_by_field_name("name")
                if name_node:
                    return name_node.text.decode('utf-8')
            elif function_node.type in ["function_expression", "arrow_function"]:
                # Anonymous functions - look for variable assignment
                parent = function_node.parent
                if parent and parent.type == "variable_declarator":
                    name_node = parent.child_by_field_name("name")
                    if name_node:
                        return name_node.text.decode('utf-8')

            return None
        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting context name: {e}")
            return None

    def _extract_class_name(self, class_node) -> Optional[str]:
        """Extract class name from class declaration node."""
        try:
            name_node = class_node.child_by_field_name("name")
            if name_node:
                return name_node.text.decode('utf-8')
            return None
        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting class name: {e}")
            return None

    def _get_file_qname_from_root(self, node) -> Optional[str]:
        """Get the file qualified name by walking to the root.

        This is a helper method to get the file context.
        In a real implementation, this would be passed in or derived from the indexing context.
        """
        try:
            # Walk up to find the program node
            current = node
            while current and current.type != "program":
                current = current.parent

            if current and current.type == "program":
                # In a real implementation, we'd have access to the file path
                # For now, return a placeholder
                return "current_file.js"

            return None
        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error getting file qname: {e}")
            return None

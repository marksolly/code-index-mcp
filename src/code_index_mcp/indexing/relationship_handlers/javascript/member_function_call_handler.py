from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_member_function_call_handler import BaseMemberFunctionCallHandler


class JavascriptMemberFunctionCallHandler(BaseMemberFunctionCallHandler):
    """JavaScript-specific implementation of member function call relationship handler."""

    def _get_member_call_queries(self) -> list[str]:
        """Return JavaScript-specific tree-sitter queries for finding member function calls."""
        return ["""
            (call_expression
                function: (member_expression
                    property: (property_identifier) @function_attr
                )
            ) @call
        """]

    def _extract_member_call_from_node(self, call_node, function_attr_node) -> Optional[dict]:
        """Extract member function call details from JavaScript AST nodes.

        Args:
            call_node: Tree-sitter node representing the call_expression
            function_attr_node: Tree-sitter node representing the property_identifier (method name)

        Returns:
            dict with method_name, object_name, and optional context info, or None if extraction fails
        """
        try:
            # Debug: Log node structure
            self.logger.log(self.__class__.__name__, f"DEBUG: Call expression node type: {call_node.type}")
            self.logger.log(self.__class__.__name__, f"DEBUG: Function attr node type: {function_attr_node.type}")

            # Extract method name from the property identifier
            method_name = function_attr_node.text.decode('utf-8')
            self.logger.log(self.__class__.__name__, f"DEBUG: Method name: {method_name}")

            # Extract object name from the member expression
            member_expr = call_node.child_by_field_name("function")
            if not member_expr or member_expr.type != "member_expression":
                self.logger.log(self.__class__.__name__, "DEBUG: No member expression found")
                return None

            object_node = member_expr.child_by_field_name("object")
            if not object_node:
                self.logger.log(self.__class__.__name__, "DEBUG: No object found in member expression")
                return None

            object_name = self._extract_object_name(object_node)
            if not object_name:
                self.logger.log(self.__class__.__name__, "DEBUG: Could not extract object name")
                return None

            self.logger.log(self.__class__.__name__, f"DEBUG: Object name: {object_name}")

            # Find the containing context (class and method)
            context_info = self._find_containing_context_for_member_call(call_node)

            result = {
                'method_name': method_name,
                'object_name': object_name
            }

            if context_info:
                result.update(context_info)

            self.logger.log(self.__class__.__name__, f"DEBUG: Extracted member call: {object_name}.{method_name} from {context_info}")
            return result

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting member call from node: {e}")
            return None

    def _extract_object_name(self, object_node) -> Optional[str]:
        """Extract the object name from an object node.

        Handles different object types:
        - this
        - identifier (variable name)
        - member_expression (chained access like this.engine)
        """
        try:
            if object_node.type == "this":
                return "this"
            elif object_node.type == "identifier":
                return object_node.text.decode('utf-8')
            elif object_node.type == "member_expression":
                # Handle chained member access like this.engine
                object_part = object_node.child_by_field_name("object")
                property_part = object_node.child_by_field_name("property")

                if object_part and property_part:
                    object_name = self._extract_object_name(object_part)
                    property_name = property_part.text.decode('utf-8') if hasattr(property_part, 'text') else str(property_part)
                    if object_name:
                        return f"{object_name}.{property_name}"

                self.logger.log(self.__class__.__name__, f"DEBUG: Could not extract chained object name from: {object_node.text.decode('utf-8') if object_node.text else 'no text'}")
                return None
            else:
                self.logger.log(self.__class__.__name__, f"DEBUG: Unsupported object type: {object_node.type}")
                return None
        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting object name: {e}")
            return None

    def _find_containing_context_for_member_call(self, node) -> Optional[dict]:
        """Find the containing context (class and method) for a member function call.

        Args:
            node: The call expression node

        Returns:
            dict with 'class_name' and 'calling_method_name', or None if not in a method
        """
        try:
            # Walk up the AST to find containing method/class
            current = node.parent

            while current:
                if current.type == "method_definition":
                    # Found a method context
                    method_name = self._extract_method_name(current)
                    class_name = self._find_containing_class(current)

                    if method_name:
                        result = {'calling_method_name': method_name}
                        if class_name:
                            result['class_name'] = class_name
                        return result
                    else:
                        return {'calling_method_name': 'method'}
                elif current.type in ["function_declaration", "function_expression", "arrow_function"]:
                    # Found a function context (not in a class)
                    function_name = self._extract_function_name(current)
                    if function_name:
                        return {'calling_method_name': function_name}
                    else:
                        return {'calling_method_name': 'function'}
                elif current.type == "class_declaration":
                    # Found a class but no method (shouldn't happen for member calls)
                    break
                elif current.type == "program":
                    # At module level
                    break

                current = current.parent

            # If no specific context found
            return None

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error finding containing context: {e}")
            return None

    def _extract_method_name(self, method_node) -> Optional[str]:
        """Extract method name from method definition node."""
        try:
            name_node = method_node.child_by_field_name("name")
            if name_node:
                return name_node.text.decode('utf-8')
            return None
        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting method name: {e}")
            return None

    def _extract_function_name(self, function_node) -> Optional[str]:
        """Extract function name from function node."""
        try:
            if function_node.type == "function_declaration":
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
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting function name: {e}")
            return None

    def _find_containing_class(self, node) -> Optional[str]:
        """Find the containing class for a node."""
        try:
            current = node.parent

            while current:
                if current.type == "class_declaration":
                    for child in current.children:
                        if child.type == 'identifier':
                            return child.text.decode('utf-8')
                elif current.type == "program":
                    break

                current = current.parent

            return None
        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error finding containing class: {e}")
            return None

    def _find_this_method(self, method_name: str, reader: 'IndexReader'):
        """
        Find a method call on 'this' object, prioritizing methods in the current class context.

        For JavaScript, we need to know which class we're calling 'this.method()' from.
        Since the base class doesn't pass this context, we need to work around it.

        Args:
            method_name: The method name (e.g., "get_identifier")
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Looking for 'this.{method_name}' method in JavaScript")

        # Find all methods with this name
        method_symbols = reader.find_symbols(name=method_name, language=self.language)
        method_symbols = [s for s in method_symbols if s['symbol_type'] == 'method']

        if not method_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: No methods found with name '{method_name}'")
            return None

        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(method_symbols)} methods with name '{method_name}'")

        # For 'this' method calls, we should prioritize methods in the current class
        # However, the base class doesn't pass the calling context to this method
        # As a workaround, we'll look for methods that might be in the same class
        # by checking if there are multiple methods with the same name in different classes

        # Group methods by their containing class
        methods_by_class = {}
        for method in method_symbols:
            qname_parts = method['qname'].split('.')
            if len(qname_parts) == 2:
                class_name = qname_parts[0]
                if class_name not in methods_by_class:
                    methods_by_class[class_name] = []
                methods_by_class[class_name].append(method)

        self.logger.log(self.__class__.__name__, f"DEBUG: Methods grouped by class: {list(methods_by_class.keys())}")

        # If we have methods in multiple classes, we need a heuristic
        # For now, prefer methods that are likely to be in the calling class
        # This is a simplified approach - in a full implementation we'd need
        # to pass the calling context from the base class

        # Look for classes that have both the method and a 'drive' method (our calling context)
        for class_name, methods in methods_by_class.items():
            # Check if this class also has a 'drive' method
            drive_methods = reader.find_symbols(qname=f"{class_name}.drive", language=self.language)
            if drive_methods:
                self.logger.log(self.__class__.__name__, f"DEBUG: Found 'drive' method in class '{class_name}', prioritizing this class's '{method_name}' method")
                return methods[0]  # Return the method from this class

        # Fallback: return the first method found
        self.logger.log(self.__class__.__name__, f"DEBUG: No clear class context found, returning first method: {method_symbols[0]['qname']}")
        return method_symbols[0]

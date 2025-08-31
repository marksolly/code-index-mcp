from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_instantiation_handler import BaseInstantiationHandler


class JavascriptInstantiationHandler(BaseInstantiationHandler):
    """JavaScript-specific implementation of instantiation relationship handler."""

    def _get_instantiation_queries(self) -> list[str]:
        """Return JavaScript-specific tree-sitter queries for finding instantiations."""
        return ["""
            (new_expression) @instantiation
        """]

    def _extract_instantiation_from_node(self, node) -> Optional[dict]:
        """Extract instantiation details from a JavaScript AST node.

        Args:
            node: Tree-sitter node representing a new_expression

        Returns:
            dict with 'class_name', or None if extraction fails
        """
        try:
            # Debug: Log node structure
            self.logger.log(self.__class__.__name__, f"DEBUG: New expression node type: {node.type}")
            self.logger.log(self.__class__.__name__, f"DEBUG: New expression children: {[(c.type, c.text.decode('utf-8') if c.text else 'no text') for c in node.children]}")

            # Find the constructor (first child after 'new' keyword)
            constructor = None
            for child in node.children:
                if child.type not in ['new', '(', ')']:
                    constructor = child
                    break

            if not constructor:
                self.logger.log(self.__class__.__name__, "DEBUG: No constructor found in new expression")
                return None

            # Extract class name from constructor
            class_name = self._extract_class_name_from_constructor(constructor)

            if class_name:
                self.logger.log(self.__class__.__name__, f"DEBUG: Extracted instantiation: {class_name}")
                return {'class_name': class_name}
            else:
                self.logger.log(self.__class__.__name__, "DEBUG: Could not extract class name from constructor")
                return None

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting instantiation from node: {e}")
            return None

    def _extract_class_name_from_constructor(self, constructor_node) -> Optional[str]:
        """Extract class name from constructor node.

        Handles different constructor patterns:
        - Simple identifier: new ClassName()
        - Member expression: new module.ClassName()
        - Property access: new obj.ClassName
        """
        try:
            if constructor_node.type == "identifier":
                # Simple case: new ClassName()
                return constructor_node.text.decode('utf-8')
            elif constructor_node.type == "member_expression":
                # Complex case: new module.ClassName() or new obj.property
                # For now, extract the last part (property name)
                # This handles cases like new module.ClassName
                property_node = constructor_node.child_by_field_name("property")
                if property_node and property_node.type == "property_identifier":
                    return property_node.text.decode('utf-8')
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Could not extract property from member expression: {constructor_node.text.decode('utf-8') if constructor_node.text else 'no text'}")
                    return None
            else:
                self.logger.log(self.__class__.__name__, f"DEBUG: Unsupported constructor type: {constructor_node.type}")
                return None
        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting class name from constructor: {e}")
            return None

    def _find_containing_context(self, node, file_qname: str) -> Optional[str]:
        """Find the containing context (function/method) for an instantiation.

        Args:
            node: The instantiation node
            file_qname: The file qualified name

        Returns:
            The qname of the containing function/method, or file_qname if at module level
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
                        # Extract clean filename from file_qname (remove :__FILE__ suffix if present)
                        clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                        return f"{clean_file_name}:{function_name}"
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
                return f"{class_context}.{method_context or 'constructor'}"
            elif method_context:
                # We're in a standalone function
                clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                return f"{clean_file_name}:{method_context}"
            else:
                # At module level or couldn't determine context
                return file_qname

            # If no specific context found, return file-level context
            return file_qname

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error finding containing context: {e}")
            return file_qname

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

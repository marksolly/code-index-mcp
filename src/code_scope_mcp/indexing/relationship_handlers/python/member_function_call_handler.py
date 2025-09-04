from typing import TYPE_CHECKING, Any, Optional, Dict

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_member_function_call_handler import BaseMemberFunctionCallHandler
from ...writer import IndexWriter
from ...reader import IndexReader


class PythonMemberFunctionCallHandler(BaseMemberFunctionCallHandler):
    """Python-specific implementation of member function call relationship handler."""

    # Map of common built-in methods to their corresponding types
    BUILTIN_METHODS = {
        'append': 'list',
        'extend': 'list',
        'insert': 'list',
        'pop': 'list',
        'remove': 'list',
        'clear': 'list',
        'sort': 'list',
        'reverse': 'list',
        'keys': 'dict',
        'values': 'dict',
        'items': 'dict',
        'get': 'dict',
        'update': 'dict',
        'log': 'console',  # JavaScript console
    }

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle Python-specific complex resolution including built-in method calls.

        For Python, we need to handle built-in method calls where the type inference
        isn't available through instantiation relationships (e.g., local variables).
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Python resolve_complex CALLED for language {self.language}!")

        # First call the parent's complex resolution
        super().resolve_complex(writer, reader)

        # Then handle Python-specific resolution
        unresolved = reader.find_unresolved("calls_class_method", language=self.language)

        self.logger.log(self.__class__.__name__, f"DEBUG: Python handler found {len(unresolved)} unresolved calls_class_method relationships in Phase 3")

        for rel in unresolved:
            method_name = rel['target_name']
            intermediate_qname = rel['intermediate_symbol_qname']

            # Try to resolve built-in method calls
            if method_name and self._try_resolve_builtin_method(writer, rel, method_name, intermediate_qname or ''):
                continue

    def _try_resolve_builtin_method(self, writer: 'IndexWriter', rel, method_name: str, intermediate_qname: str) -> bool:
        """
        Try to resolve a method call to a built-in Python type.

        Args:
            writer: IndexWriter instance
            rel: Unresolved relationship (sqlite3.Row or dict-like object)
            method_name: Name of the method being called
            intermediate_qname: The intermediate qname (e.g., "self.cars.append")

        Returns:
            True if resolved as built-in, False otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Attempting to resolve built-in method: {intermediate_qname}")

        # Check if this is a known built-in method
        if method_name not in self.BUILTIN_METHODS:
            return False

        builtin_type = self.BUILTIN_METHODS[method_name]

        # Create a synthetic qname for the built-in method
        builtin_qname = f"{builtin_type}.{method_name}"

        self.logger.log(self.__class__.__name__, f"DEBUG: Creating synthetic builtin method: {builtin_qname}")

        # For built-in methods, we just mark the unresolved relationship as resolved
        # since these methods don't exist as symbols in the source code
        writer.delete_unresolved_relationship(rel['id'])

        self.logger.log(self.__class__.__name__, f"DEBUG: Resolved built-in method call: {rel['source_qname']} -> {builtin_qname} (marked as resolved)")
        return True
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

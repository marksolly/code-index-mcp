from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..common.base_member_function_call_handler import BaseMemberFunctionCallHandler


class PhpMemberFunctionCallHandler(BaseMemberFunctionCallHandler):
    """PHP-specific implementation of member function call relationship handler."""

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """Extract member function call relationships from AST."""
        self.logger.log(self.__class__.__name__, f"DEBUG: extract_from_ast called for {file_qname}")

        # Get language-specific member function call queries
        member_call_queries = self._get_member_call_queries()
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(member_call_queries)} queries")

        for query_text in member_call_queries:
            self.logger.log(self.__class__.__name__, f"DEBUG: Executing query: {query_text.strip()}")
            query = self.language_obj.query(query_text)
            captures = query.captures(tree.root_node)
            self.logger.log(self.__class__.__name__, f"DEBUG: Query returned {len(captures)} captures")

            # Group captures by node for easier processing
            capture_groups = {}
            for node, capture_name in captures:
                if capture_name not in capture_groups:
                    capture_groups[capture_name] = []
                capture_groups[capture_name].append(node)

            self.logger.log(self.__class__.__name__, f"DEBUG: Capture groups: {list(capture_groups.keys())}")
            self.logger.log(self.__class__.__name__, f"DEBUG: Call nodes: {len(capture_groups.get('call', []))}")
            self.logger.log(self.__class__.__name__, f"DEBUG: Function attr nodes: {len(capture_groups.get('function_attr', []))}")

            # Process each member call
            call_nodes = capture_groups.get("call", [])
            function_attr_nodes = capture_groups.get("function_attr", [])

            self.logger.log(self.__class__.__name__, f"DEBUG: Processing {len(call_nodes)} member calls")

            for i, call_node in enumerate(call_nodes):
                if i >= len(function_attr_nodes):
                    self.logger.log(self.__class__.__name__, f"DEBUG: Skipping call {i} - no matching function_attr")
                    continue

                function_attr = function_attr_nodes[i]
                self.logger.log(self.__class__.__name__, f"DEBUG: Processing call {i}: {call_node.text.decode('utf-8')} -> {function_attr.text.decode('utf-8')}")

                # Extract call details using language-specific method
                call_details = self._extract_member_call_from_node(call_node, function_attr)
                if not call_details:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Failed to extract call details for call {i}")
                    continue

                self.logger.log(self.__class__.__name__, f"DEBUG: Extracted call details: {call_details}")

                # Construct source_qname from the extracted details
                source_qname = self._construct_source_qname(call_details, file_qname)
                self.logger.log(self.__class__.__name__, f"DEBUG: Constructed source_qname: '{source_qname}'")

                if not source_qname:
                    self.logger.log(self.__class__.__name__, f"DEBUG: No source_qname constructed")
                    continue

                # Find source symbol
                source_symbols = reader.find_symbols(qname=source_qname, language=self.language)
                self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(source_symbols)} source symbols for qname '{source_qname}'")

                if source_symbols:
                    source_symbol_id = source_symbols[0]['id']
                    self.logger.log(self.__class__.__name__, f"DEBUG: Creating unresolved relationship for source_symbol_id {source_symbol_id}")

                    # Create intermediate_symbol_qname
                    intermediate_qname = f"{call_details['object_name']}.{call_details['method_name']}"
                    self.logger.log(self.__class__.__name__, f"DEBUG: Intermediate qname: '{intermediate_qname}'")

                    writer.add_unresolved_relationship(
                        source_symbol_id=source_symbol_id,
                        source_qname=source_qname,
                        target_name=call_details['method_name'],
                        rel_type="calls_class_method",
                        needs_type="declares_class_method",
                        target_qname=None,
                        intermediate_symbol_qname=intermediate_qname
                    )
                    self.logger.log(self.__class__.__name__, f"DEBUG: Unresolved relationship created")
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Source symbol not found: {source_qname}")

        self.logger.log(self.__class__.__name__, f"DEBUG: extract_from_ast completed for {file_qname}")
        return None

    def _get_member_call_queries(self) -> list[str]:
        """Return PHP-specific tree-sitter queries for finding member function calls."""
        return [
            # Query for member call expressions with captures expected by base class
            """
            (member_call_expression
              object: (_) @object
              name: (name) @function_attr
            ) @call
            """
        ]

    def _extract_member_call_from_node(self, call_node, function_attr_node) -> Optional[dict]:
        """Extract member function call details from AST nodes.

        Args:
            call_node: Tree-sitter node representing the member_call_expression
            function_attr_node: Tree-sitter node representing the method name (name node)

        Returns:
            dict with required keys for BaseMemberFunctionCallHandler, or None if extraction fails
        """
        try:
            self.logger.log(self.__class__.__name__, f"DEBUG: _extract_member_call_from_node called")
            self.logger.log(self.__class__.__name__, f"DEBUG: call_node type: {call_node.type}, text: '{call_node.text.decode('utf-8')}'")
            self.logger.log(self.__class__.__name__, f"DEBUG: function_attr_node type: {function_attr_node.type}, text: '{function_attr_node.text.decode('utf-8')}'")

            # Extract object name from call_node
            object_node = call_node.child_by_field_name("object")
            if not object_node:
                self.logger.log(self.__class__.__name__, f"DEBUG: No object node found")
                return None

            self.logger.log(self.__class__.__name__, f"DEBUG: object_node type: {object_node.type}, text: '{object_node.text.decode('utf-8')}'")

            object_name = None
            if object_node.type == "variable_name":
                # For variable_name nodes, the name might be a direct child or the text itself
                name_node = object_node.child_by_field_name("name")
                if name_node:
                    object_name = name_node.text.decode('utf-8')
                else:
                    # If no name child, use the text directly (for $this, $car, etc.)
                    object_name = object_node.text.decode('utf-8')
            elif object_node.type == "name":
                object_name = object_node.text.decode('utf-8')
            elif object_node.type == "member_access_expression":
                # Handle chained access like $this->engine
                object_name = object_node.text.decode('utf-8')

            self.logger.log(self.__class__.__name__, f"DEBUG: Extracted object_name: '{object_name}'")

            if not object_name:
                return None

            # Clean up object_name for the intermediate_symbol_qname
            # Remove $ prefix for PHP variables and map $this to self
            clean_object_name = object_name.lstrip('$') if object_name.startswith('$') else object_name
            if clean_object_name == 'this':
                clean_object_name = 'self'  # Map PHP's $this to the base class expected 'self'
            self.logger.log(self.__class__.__name__, f"DEBUG: Cleaned object_name: '{clean_object_name}'")

            # Extract method name from function_attr_node
            method_name = function_attr_node.text.decode('utf-8')
            self.logger.log(self.__class__.__name__, f"DEBUG: Extracted method_name: '{method_name}'")

            # Find containing context (class and method names)
            class_name, calling_method_name = self._find_calling_context(call_node)
            self.logger.log(self.__class__.__name__, f"DEBUG: Found context - class: '{class_name}', method: '{calling_method_name}'")

            result = {
                'method_name': method_name,
                'object_name': clean_object_name,  # Use cleaned name for base class
                'class_name': class_name,
                'calling_method_name': calling_method_name
            }
            self.logger.log(self.__class__.__name__, f"DEBUG: Returning result: {result}")
            return result

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting member call from nodes: {e}")
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

    def _find_containing_context(self, node, file_qname: str) -> Optional[str]:
        """Find the containing context (function/method) for a member call.

        Args:
            node: Tree-sitter node representing the member call
            file_qname: The file qualified name

        Returns:
            The qname of the containing function/method, or the file qname if at global level.
            Returns None if context cannot be determined.
        """
        try:
            current = node.parent
            while current:
                if current.type == "method_declaration":
                    # Get method name
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        method_name = name_node.text.decode('utf-8')

                        # Find the containing class
                        class_name = None
                        parent = current.parent
                        while parent:
                            if parent.type == "class_declaration":
                                class_name_node = parent.child_by_field_name("name")
                                if class_name_node:
                                    class_name = class_name_node.text.decode('utf-8')
                                break
                            parent = parent.parent

                        if class_name:
                            return f"{class_name}.{method_name}"

                elif current.type == "function_definition":
                    # Get function name
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        function_name = name_node.text.decode('utf-8')

                        # Extract clean filename from file_qname (remove :__FILE__ suffix if present)
                        clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                        return f"{clean_file_name}:{function_name}"

                current = current.parent

            # If no containing function/method found, return file qname
            return file_qname

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error finding containing context: {e}")
            return file_qname

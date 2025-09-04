from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler


class BaseMemberFunctionCallHandler(BaseRelationshipHandler, ABC):
    """Abstract base class for member function call relationship handlers.

    This class contains the reusable logic for member function call resolution while
    delegating language-specific AST parsing and queries to subclasses.
    """

    relationship_type = "calls_class_method"

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved call relationships from AST for member function calls.

        PRIMARY PURPOSE: Analyze AST syntax to identify member function call candidates.
        READING FROM DATABASE: Allowed only as last resort for finding source symbol IDs.

        ⚠️  DATABASE READS SHOULD BE MINIMAL:
           - Only query for source symbol IDs by qname
           - Avoid complex lookups or relationship queries
           - Defer all resolution logic to Phase 2

        Creates unresolved relationships for member function calls.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseMemberFunctionCallHandler.extract_from_ast called")

        # Get language-specific member function call queries
        member_call_queries = self._get_member_call_queries()

        for query_text in member_call_queries:
            query = self.language_obj.query(query_text)
            captures = query.captures(tree.root_node)

            # Group captures by node for easier processing
            capture_groups = {}
            for node, capture_name in captures:
                if capture_name not in capture_groups:
                    capture_groups[capture_name] = []
                capture_groups[capture_name].append(node)

            # Process each member call
            call_nodes = capture_groups.get("call", [])
            function_attr_nodes = capture_groups.get("function_attr", [])

            for i, call_node in enumerate(call_nodes):
                if i >= len(function_attr_nodes):
                    continue

                function_attr = function_attr_nodes[i]

                # Extract call details using language-specific method
                call_details = self._extract_member_call_from_node(call_node, function_attr)
                if not call_details:
                    continue

                method_name = call_details['method_name']
                object_name = call_details['object_name']

                # Construct source_qname from the extracted details
                source_qname = self._construct_source_qname(call_details, file_qname)
                if not source_qname:
                    continue

                # ⚠️  LAST RESORT: Find source symbol ID using reader
                source_symbols = reader.find_symbols(qname=source_qname, language=self.language)
                if source_symbols:
                    source_symbol_id = source_symbols[0]['id']
                    self.logger.log(self.__class__.__name__, f"DEBUG: Found source symbol id: {source_symbol_id}, creating unresolved relationship")
                    writer.add_unresolved_relationship(
                        source_symbol_id=source_symbol_id,
                        source_qname=source_qname,
                        target_name=method_name,
                        rel_type="calls_class_method",
                        needs_type="declares_class_method",
                        target_qname=None,
                        intermediate_symbol_qname=f"{object_name}.{method_name}"  # Store object.method for resolution
                    )
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Source symbol not found: {source_qname}")

    @abstractmethod
    def _get_member_call_queries(self) -> list[str]:
        """Return language-specific tree-sitter queries for finding member function calls."""
        pass

    @abstractmethod
    def _extract_member_call_from_node(self, call_node, function_attr_node) -> Optional[dict]:
        """Extract member function call details from AST nodes.

        Returns:
            dict with keys:
            - 'method_name': str - the name of the method being called
            - 'object_name': str - the object/variable being called on
            - 'class_name': str - the class name if in a class method (optional)
            - 'calling_method_name': str - the calling method name (optional)
            Returns None if extraction fails.
        """
        pass

    def _construct_source_qname(self, call_details: dict, file_qname: str) -> Optional[str]:
        """
        Construct the source qualified name from extracted call details.

        Args:
            call_details: Dict returned by _extract_member_call_from_node
            file_qname: The qualified name of the file

        Returns:
            The source qualified name, or None if construction fails
        """
        class_name = call_details.get('class_name')
        calling_method_name = call_details.get('calling_method_name')

        if class_name and calling_method_name:
            # This is a class method
            return f"{class_name}.{calling_method_name}"
        elif calling_method_name:
            # This is a standalone function (no class context)
            # Strip :__FILE__ suffix from file_qname if present
            base_file_qname = file_qname
            if base_file_qname.endswith(':__FILE__'):
                base_file_qname = base_file_qname.rsplit(':__FILE__', 1)[0]  # Remove ':__FILE__'
            return f"{base_file_qname}:{calling_method_name}"
        else:
            # Could not determine calling context
            self.logger.log(self.__class__.__name__, f"DEBUG: Could not determine source context for call")
            return None

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Resolve member function calls with current knowledge.

        Can resolve method calls within the same class and through inheritance.
        This logic is language-agnostic and reusable across languages.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseMemberFunctionCallHandler.resolve_immediate called")
        # Query unresolved 'calls_class_method' relationships for this language only
        unresolved = reader.find_unresolved("calls_class_method", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved calls_class_method relationships")

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Processing unresolved relationship: {rel['source_qname']} -> {rel['target_name']} (intermediate: {rel['intermediate_symbol_qname']})")

            if rel['intermediate_symbol_qname']:
                # Try to find the target symbol, considering inheritance and calling context
                target_symbol = self._find_method_with_inheritance(rel['intermediate_symbol_qname'], rel['source_qname'], reader)

                if target_symbol:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved relationship: {rel['source_qname']} -> {target_symbol['qname']}")
                    # Create resolved relationship
                    writer.add_relationship(
                        source_symbol_id=rel['source_symbol_id'],
                        target_symbol_id=target_symbol['id'],
                        rel_type="calls_class_method",
                        source_qname=rel['source_qname'],
                        target_qname=target_symbol['qname']
                    )
                    # Delete the unresolved relationship
                    writer.delete_unresolved_relationship(rel['id'])
                    self.logger.log(self.__class__.__name__, "DEBUG: Relationship resolved and unresolved deleted")
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: No target symbols found for {rel['intermediate_symbol_qname']} (including inheritance)")
            else:
                self.logger.log(self.__class__.__name__, "DEBUG: No intermediate_symbol_qname found")

    def _find_method_with_inheritance(self, intermediate_qname: str, source_qname: str, reader: 'IndexReader'):
        """
        Find a method symbol, considering inheritance relationships.

        This is generic logic that works across languages.

        Args:
            intermediate_qname: The qname to search for (e.g., "self.start", "self.engine.start_engine")
            source_qname: The qname of the calling method (e.g., "Car.drive")
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Looking for method with inheritance: {intermediate_qname} (from {source_qname})")

        # Parse the intermediate qname to extract object and method
        # The format is "object.method" where object could be "self" or "self.something"
        if '.' not in intermediate_qname:
            self.logger.log(self.__class__.__name__, f"DEBUG: Invalid intermediate_qname format: {intermediate_qname}")
            return None

        # Split from the right to get the method name and the full object path
        parts = intermediate_qname.rsplit('.', 1)
        if len(parts) != 2:
            self.logger.log(self.__class__.__name__, f"DEBUG: Invalid intermediate_qname format: {intermediate_qname}")
            return None

        object_name = parts[0]  # e.g., "self" or "self.engine"
        method_name = parts[1]  # e.g., "start" or "start_engine"

        # Handle different object types
        if object_name == "self":
            # self.method() - find method in current class or inherited classes
            return self._find_self_method_with_inheritance(intermediate_qname, method_name, source_qname, reader)
        elif object_name.startswith('self.'):
            # self.instance_var.method() - find method in the instance variable's class
            return self._find_instance_variable_method(intermediate_qname, object_name, method_name, source_qname, reader)
        else:
            # obj.method() - find method in the object's class
            return self._find_object_method(intermediate_qname, object_name, method_name, reader)

    def _find_self_method_with_inheritance(self, intermediate_qname: str, method_name: str, source_qname: str, reader: 'IndexReader'):
        """
        Find a self method call, considering inheritance and calling context.

        This is generic logic that works across languages.

        Args:
            intermediate_qname: The full intermediate qname (e.g., "self.start")
            method_name: The method name (e.g., "start")
            source_qname: The qname of the calling method (e.g., "Car.drive")
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Looking for self method '{method_name}' with inheritance (from {source_qname})")

        # Try to find methods with the given name
        method_symbols = reader.find_symbols(name=method_name, language=self.language)

        # Filter for method symbols only
        method_symbols = [s for s in method_symbols if s['symbol_type'] == 'method']

        if not method_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: No methods found with name '{method_name}'")
            return None

        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(method_symbols)} methods with name '{method_name}'")

        # For self.method() calls, we need to be smarter about which method to pick
        # We should prefer methods that are in the same class as the calling method

        # Extract the calling class from source_qname (e.g., "Car.drive" -> "Car")
        source_parts = source_qname.split('.')
        if len(source_parts) == 2:
            calling_class = source_parts[0]
            self.logger.log(self.__class__.__name__, f"DEBUG: Calling method is in class '{calling_class}', looking for method in same class")

            # First priority: method in the same class
            same_class_methods = []
            for method in method_symbols:
                method_qname = method['qname']
                if method_qname.startswith(f"{calling_class}."):
                    same_class_methods.append(method)

            if same_class_methods:
                self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(same_class_methods)} methods in same class, picking: {same_class_methods[0]['qname']}")
                return same_class_methods[0]

        # Second priority: any class method (not standalone function)
        class_methods = []
        for method in method_symbols:
            qname = method['qname']
            # If the qname contains a dot, it's likely a class method (Class.method)
            if '.' in qname and not qname.endswith(':__FILE__'):
                class_methods.append(method)

        if class_methods:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(class_methods)} class methods, picking first: {class_methods[0]['qname']}")
            return class_methods[0]

        # Fallback to any method
        self.logger.log(self.__class__.__name__, f"DEBUG: No class methods found, picking first available: {method_symbols[0]['qname']}")
        return method_symbols[0]

    def _find_instance_variable_method(self, intermediate_qname: str, object_name: str, method_name: str, source_qname: str, reader: 'IndexReader'):
        """
        Find a method call on an instance variable (e.g., self.engine.start_engine()).

        This method handles complex expressions like self.Timing_data[operation].append()
        by simplifying them to their base form (self.Timing_data) before processing.
        This prevents invalid qname creation that would violate the IndexReader validation.

        This is generic logic that works across languages.

        Args:
            intermediate_qname: The full intermediate qname (e.g., "self.engine.start_engine")
            object_name: The object name (e.g., "self.engine" or "self.Timing_data[operation]")
            method_name: The method name (e.g., "start_engine")
            source_qname: The qname of the calling method (e.g., "Car.drive")
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Looking for instance variable method '{object_name}.{method_name}' (from {source_qname})")

        # BUG FIX: Handle complex expressions by simplifying them to base form
        # This prevents creation of invalid qnames like "Timing_data[operation].append"
        # which would fail IndexReader validation and crash the indexer.
        if self._is_complex_expression(object_name):
            simplified_object_name = self._simplify_complex_expression(object_name)
            self.logger.log(self.__class__.__name__, f"DEBUG: Simplified complex expression '{object_name}' to '{simplified_object_name}'")
            object_name = simplified_object_name

        # Extract the instance variable name (e.g., "self.engine" -> "engine")
        if not object_name.startswith('self.'):
            self.logger.log(self.__class__.__name__, f"DEBUG: Not an instance variable: {object_name}")
            return None

        instance_var = object_name[5:]  # Remove "self." prefix

        # Try to infer the type from the instance variable name
        # This is a heuristic: "engine" -> "Engine" class
        likely_class_name = instance_var.capitalize()

        # Look for the method in the likely class
        target_qname = f"{likely_class_name}.{method_name}"
        self.logger.log(self.__class__.__name__, f"DEBUG: Trying inferred class method: {target_qname}")

        method_symbols = reader.find_symbols(qname=target_qname, language=self.language)
        if method_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found method in inferred class: {method_symbols[0]['qname']}")
            return method_symbols[0]

        # Fallback: try to find any method with that name
        method_symbols = reader.find_symbols(name=method_name, language=self.language)

        # Filter for method symbols only
        method_symbols = [s for s in method_symbols if s['symbol_type'] == 'method']

        if method_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(method_symbols)} methods with name '{method_name}', picking first")
            return method_symbols[0]
        else:
            self.logger.log(self.__class__.__name__, f"DEBUG: No methods found with name '{method_name}'")
            return None

    def _is_complex_expression(self, expression: str) -> bool:
        """
        Check if an expression contains complex syntax that needs simplification.

        Args:
            expression: The expression to check (e.g., "self.Timing_data[operation]")

        Returns:
            True if the expression contains complex syntax, False otherwise
        """
        # Check for common complex syntax patterns
        complex_chars = ['[', '(', '{', '.']
        for char in complex_chars:
            if char in expression:
                return True
        return False

    def _simplify_complex_expression(self, complex_expression: str) -> str:
        """
        Simplify a complex expression to its base form.

        This extracts the base identifier from complex expressions like:
        - "self.Timing_data[operation]" → "self.Timing_data"
        - "self.engine.gear" → "self.engine"
        - "self.data[key].method" → "self.data"

        Args:
            complex_expression: The complex expression to simplify

        Returns:
            The simplified base expression
        """
        # Find the first occurrence of complex syntax characters
        complex_chars = ['[', '(', '{']
        min_index = len(complex_expression)

        for char in complex_chars:
            idx = complex_expression.find(char)
            if idx != -1 and idx < min_index:
                min_index = idx

        if min_index < len(complex_expression):
            # Extract the base part before the complex syntax
            base_expression = complex_expression[:min_index]
            self.logger.log(self.__class__.__name__, f"DEBUG: Simplified '{complex_expression}' to '{base_expression}'")
            return base_expression
        else:
            # No complex syntax found, return as-is
            return complex_expression

    def _find_object_method(self, intermediate_qname: str, object_name: str, method_name: str, reader: 'IndexReader'):
        """
        Find an object method call.

        This is generic logic that works across languages.

        Args:
            intermediate_qname: The full intermediate qname (e.g., "my_garage.service_car")
            object_name: The object name (e.g., "my_garage")
            method_name: The method name (e.g., "service_car")
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Looking for object method '{object_name}.{method_name}'")

        # Handle 'this' method calls specially - these should prioritize the current class
        if object_name == "this":
            return self._find_this_method(method_name, reader)

        # Try to resolve the variable type through instantiation relationships
        variable_type = self._resolve_variable_type(object_name, reader)
        if variable_type:
            self.logger.log(self.__class__.__name__, f"DEBUG: Resolved variable '{object_name}' to type '{variable_type}'")

            # Look for the method in the resolved class
            target_qname = f"{variable_type}.{method_name}"
            method_symbols = reader.find_symbols(qname=target_qname, language=self.language)
            if method_symbols:
                self.logger.log(self.__class__.__name__, f"DEBUG: Found method in resolved class: {method_symbols[0]['qname']}")
                return method_symbols[0]

        # Handle instance variable method calls (e.g., self.engine.start_engine())
        if object_name.startswith('self.'):
            # Extract the instance variable name (e.g., "self.engine" -> "engine")
            instance_var = object_name[5:]  # Remove "self." prefix

            # Try to infer the type from the instance variable name
            # This is a heuristic: "engine" -> "Engine" class
            likely_class_name = instance_var.capitalize()

            # Look for the method in the likely class
            target_qname = f"{likely_class_name}.{method_name}"
            self.logger.log(self.__class__.__name__, f"DEBUG: Trying inferred class method: {target_qname}")

            method_symbols = reader.find_symbols(qname=target_qname, language=self.language)
            if method_symbols:
                self.logger.log(self.__class__.__name__, f"DEBUG: Found method in inferred class: {method_symbols[0]['qname']}")
                return method_symbols[0]

        # Fallback: try to find any method with that name
        method_symbols = reader.find_symbols(name=method_name, language=self.language)

        # Filter for method symbols only
        method_symbols = [s for s in method_symbols if s['symbol_type'] == 'method']

        if method_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(method_symbols)} methods with name '{method_name}', picking first")
            # For now, return the first one found
            return method_symbols[0]
        else:
            self.logger.log(self.__class__.__name__, f"DEBUG: No methods found with name '{method_name}'")
            return None

    def _find_this_method(self, method_name: str, reader: 'IndexReader'):
        """
        Find a method call on 'this' object, prioritizing methods in the current class context.

        This method should be called from subclasses with proper context information.
        For now, this is a simplified implementation that just finds any method with the name.

        Args:
            method_name: The method name (e.g., "get_identifier")
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Looking for 'this.{method_name}' method")

        # For 'this' method calls, we need context about which class we're in
        # This is a limitation of the current base class design
        # Subclasses should override this method with proper context awareness

        # Fallback: find any method with this name
        method_symbols = reader.find_symbols(name=method_name, language=self.language)
        method_symbols = [s for s in method_symbols if s['symbol_type'] == 'method']

        if method_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(method_symbols)} methods with name '{method_name}', picking first")
            return method_symbols[0]
        else:
            self.logger.log(self.__class__.__name__, f"DEBUG: No methods found with name '{method_name}'")
            return None

    def _resolve_variable_type(self, variable_name: str, reader: 'IndexReader'):
        """
        Resolve the type of a variable by looking at instantiation relationships.

        This is generic logic that works across languages.

        Args:
            variable_name: The variable name (e.g., "my_garage")
            reader: IndexReader instance

        Returns:
            Class name if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Resolving type of variable '{variable_name}'")

        # Look for instantiation relationships where this variable is the target
        # This is a simplified approach - in a full implementation we'd need
        # more sophisticated variable tracking

        # For now, we'll look for any instantiation that might be related
        # This is a heuristic and may not work for all cases

        # Try to find instantiations in the current context
        # This is a basic heuristic that looks for recent instantiations
        instantiation_rels = reader.find_relationships(
            rel_type="instantiates",
            source_language=self.language,
            target_language=self.language
        )

        for rel in instantiation_rels:
            # Look for patterns like variable assignments
            # This is very basic and would need enhancement for production use
            source_qname = rel['source_qname']
            target_qname = rel['target_qname']

            # If the source contains the variable name, it might be an instantiation of that variable
            if variable_name in source_qname:
                # Extract the class name from the target
                # target_qname format is like "file2.py:Car" or "file3.py:Garage"
                if ':' in target_qname:
                    # Split by ':' and take the last part, then remove any remaining dots
                    parts = target_qname.split(':')
                    if len(parts) >= 2:
                        class_part = parts[-1]  # Get the part after the last ':'
                        if '.' in class_part:
                            class_name = class_part.split('.')[-1]  # Get the last part after '.'
                        else:
                            class_name = class_part
                        self.logger.log(self.__class__.__name__, f"DEBUG: Found potential class '{class_name}' for variable '{variable_name}'")
                        return class_name
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Found potential class '{target_qname}' for variable '{variable_name}'")
                    return target_qname

        self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve type for variable '{variable_name}'")
        return None

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle complex member function call resolution.

        This generic handler doesn't implement complex resolution.
        Language-specific subclasses can override this method if needed.
        """
        # Query remaining unresolved 'calls_class_method' relationships
        unresolved = reader.find_unresolved("calls_class_method", language=self.language)

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Complex resolution needed for: {rel['source_qname']} -> {rel['target_name']}")

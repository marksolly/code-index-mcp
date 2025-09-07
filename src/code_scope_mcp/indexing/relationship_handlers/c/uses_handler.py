from typing import TYPE_CHECKING, Any, Optional, List

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler


class CUsesRelationshipHandler(BaseRelationshipHandler):
    """C-specific implementation of uses relationship handler for custom types."""

    relationship_type = "uses"
    phase_dependencies = ["imports"]  # Need type symbols to be available

    def __init__(self, language: str, language_obj, logger):
        super().__init__(language, language_obj, logger)
        self.logger.log(self.__class__.__name__, f"DEBUG: CUsesRelationshipHandler initialized for language {language}")

    def extract_from_ast(self, tree: 'Tree', writer, reader, file_qname: str):
        """
        Phase 1: Extract unresolved 'uses' relationships for local variables of custom types.

        Finds local variables and function parameters that are instances of custom types
        (struct, enum, typedef) and creates 'uses' relationships to their type symbols.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: CUsesRelationshipHandler.extract_from_ast called")

        # Track created relationships to avoid duplicates
        created_relationships = set()

        # Find all variable declarations that could be of custom types
        declaration_query = """
            (declaration) @declaration
        """

        query = self.language_obj.query(declaration_query)
        captures = query.captures(tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "declaration":
                # Process this declaration to find variables of custom types
                self._process_declaration(node, tree, writer, reader, file_qname, created_relationships)

        # Also find function parameters
        parameter_query = """
            (parameter_declaration) @parameter
        """

        query = self.language_obj.query(parameter_query)
        captures = query.captures(tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "parameter":
                # Process this parameter declaration
                self._process_parameter_declaration(node, tree, writer, reader, file_qname, created_relationships)

    def _process_declaration(self, declaration_node, tree, writer, reader, file_qname, created_relationships):
        """Process a declaration node to find variables of custom types."""
        from tree_sitter import Query

        # Extract the type specifier from the declaration
        type_spec = self._extract_type_specifier(declaration_node)
        if not type_spec:
            return

        # Check if this is an interesting type (custom type, not primitive)
        if not self._is_interesting_type(type_spec):
            return

        # Find the declarator(s) in this declaration
        declarator_query = """
            (init_declarator
                declarator: (identifier) @name)
        """

        query = self.language_obj.query(declarator_query)
        captures = query.captures(declaration_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "name":
                var_name = node.text.decode('utf-8')

                # Determine the containing function context
                containing_function = self._get_containing_function(node, tree)
                if containing_function:
                    # This is a local variable in a function
                    source_qname = f"{file_qname.split(':')[0]}:{containing_function}"

                    # Create unresolved 'uses' relationship
                    self._create_uses_relationship(
                        var_name, type_spec, source_qname, writer, reader, file_qname, created_relationships
                    )
                else:
                    # Global variable - create relationship from the global variable itself
                    source_qname = f"{file_qname.split(':')[0]}:{var_name}"

                    # Create unresolved 'uses' relationship
                    self._create_uses_relationship(
                        var_name, type_spec, source_qname, writer, reader, file_qname, created_relationships
                    )

    def _process_parameter_declaration(self, parameter_node, tree, writer, reader, file_qname, created_relationships):
        """Process a parameter declaration to find parameters of custom types."""
        # Extract the type specifier from the parameter
        type_spec = self._extract_type_specifier(parameter_node)
        if not type_spec:
            return

        # Check if this is an interesting type
        if not self._is_interesting_type(type_spec):
            return

        # Find the parameter name
        declarator = parameter_node.child_by_field_name("declarator")
        if declarator:
            param_name = self._extract_parameter_name(declarator)
            if param_name:
                # Find the containing function
                containing_function = self._get_containing_function(parameter_node, tree)
                if containing_function:
                    source_qname = f"{file_qname.split(':')[0]}:{containing_function}"

                    # Create unresolved 'uses' relationship
                    self._create_uses_relationship(
                        param_name, type_spec, source_qname, writer, reader, file_qname, created_relationships
                    )

    def _extract_type_specifier(self, node):
        """Extract the type specifier from a declaration or parameter node."""
        # Look for type information in the node
        type_node = node.child_by_field_name("type")
        if type_node:
            return type_node.text.decode('utf-8').strip()

        # For some patterns, the type might be embedded differently
        # Look for primitive_type, struct_specifier, enum_specifier, etc.
        for child in node.children:
            if child.type in ["primitive_type", "struct_specifier", "enum_specifier", "type_identifier"]:
                return child.text.decode('utf-8').strip()

        return None

    def _is_interesting_type(self, type_spec: str) -> bool:
        """Determine if a type specifier represents an interesting custom type."""
        import re

        # ALWAYS TRACK (high semantic value)
        if 'struct' in type_spec or 'enum' in type_spec:
            return True  # struct Point, enum Color
        if '(*' in type_spec or 'function' in type_spec:
            return True  # Function pointers

        # NEVER TRACK (primitive aliases cause relationship bloat)
        primitive_patterns = [
            r'^(int|char|long|short|float|double|void|bool)$',
            r'^(u?int\d*_t|size_t|ptrdiff_t)$',
        ]
        for pattern in primitive_patterns:
            if re.search(pattern, type_spec):
                return False  # typedef int Integer; (problematic)

        # Check if it's a typedef that we know is interesting
        # For now, assume any remaining type_identifiers are potentially interesting typedefs
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', type_spec):
            return True  # Could be a typedef like Point, Color, etc.

        return False  # Default to not interesting

    def _create_uses_relationship(self, var_name, type_spec, source_qname, writer, reader, file_qname, created_relationships):
        """Create an unresolved 'uses' relationship for a variable using a custom type."""
        # Avoid duplicate relationships
        relationship_key = f"{source_qname}:{var_name}:{type_spec}"
        if relationship_key in created_relationships:
            return
        created_relationships.add(relationship_key)

        # Get source symbol ID (function symbol)
        source_symbols = reader.find_symbols(qname=source_qname, language=self.language)
        if source_symbols:
            source_symbol_id = source_symbols[0]['id']

            # Create unresolved relationship for the 'uses' relationship
            writer.add_unresolved_relationship(
                source_symbol_id=source_symbol_id,
                source_qname=source_qname,
                target_name=type_spec,  # The type name (e.g., "Point", "Color")
                rel_type="uses",
                needs_type="imports",  # Types are typically imported or defined in headers
                target_qname=None,
                intermediate_symbol_qname=var_name,  # The variable name for context
                target_resolver_name=self.__class__.__name__
            )
            self.logger.log(self.__class__.__name__,
                          f"DEBUG: Created unresolved 'uses' relationship: {source_qname} -> {type_spec} (via {var_name})")
        else:
            self.logger.log(self.__class__.__name__,
                          f"DEBUG: Source symbol not found for {source_qname}")

    def _extract_parameter_name(self, declarator_node):
        """Extract parameter name from various declarator patterns."""
        # For simple identifiers
        if declarator_node.type == "identifier":
            return declarator_node.text.decode('utf-8')

        # For pointer declarators like "*user"
        if declarator_node.type == "pointer_declarator":
            inner = declarator_node.child_by_field_name("declarator")
            if inner and inner.type == "identifier":
                return inner.text.decode('utf-8')

        # For array declarators like "arr[]"
        if declarator_node.type == "array_declarator":
            inner = declarator_node.child_by_field_name("declarator")
            if inner and inner.type == "identifier":
                return inner.text.decode('utf-8')

        # For function declarators (function pointers)
        if declarator_node.type == "function_declarator":
            inner = declarator_node.child_by_field_name("declarator")
            if inner and inner.type == "identifier":
                return inner.text.decode('utf-8')

        return None

    def _get_containing_function(self, node, tree) -> Optional[str]:
        """Find the containing function for a given node."""
        current = node.parent
        while current:
            if current.type == "function_definition":
                # Extract function name
                declarator = current.child_by_field_name("declarator")
                if declarator:
                    if declarator.type == "identifier":
                        return declarator.text.decode('utf-8')
                    elif declarator.type == "function_declarator":
                        func_name = declarator.child_by_field_name("declarator")
                        if func_name and func_name.type == "identifier":
                            return func_name.text.decode('utf-8')
            current = current.parent
        return None

    def resolve_immediate(self, writer, reader):
        """
        Phase 2: Resolve 'uses' relationships using import relationships.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: CUsesRelationshipHandler.resolve_immediate called")

        # Query unresolved 'uses' relationships for C language
        unresolved = reader.find_unresolved("uses", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved 'uses' relationships")

        resolved_count = 0
        for rel in unresolved:
            self.logger.log(self.__class__.__name__,
                          f"DEBUG: Processing unresolved 'uses' relationship: {rel['source_qname']} -> {rel['target_name']}")

            # Try to resolve the type reference
            target_symbol = self._resolve_type_reference(rel['target_name'], rel['source_qname'], reader)

            if target_symbol:
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Creating resolved 'uses' relationship: {rel['source_qname']} -> {target_symbol['qname']}")
                writer.add_relationship(
                    source_symbol_id=rel['source_symbol_id'],
                    target_symbol_id=target_symbol['id'],
                    rel_type="uses",
                    source_qname=rel['source_qname'],
                    target_qname=target_symbol['qname']
                )
                resolved_count += 1

                # Delete the unresolved relationship
                writer.delete_unresolved_relationship(rel['id'])
                self.logger.log(self.__class__.__name__, "DEBUG: 'uses' relationship resolved")
            else:
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Could not resolve 'uses' relationship: {rel['target_name']}")

        self.logger.log(self.__class__.__name__, f"DEBUG: Resolved {resolved_count} 'uses' relationships")

    def _resolve_type_reference(self, type_name: str, source_qname: str, reader):
        """
        Resolve a type reference to its symbol.

        For C, types are typically either:
        1. Defined in the same file
        2. Imported from header files

        Args:
            type_name: The type name being referenced
            source_qname: The source function making the reference
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__,
                      f"DEBUG: Resolving type reference {type_name} from {source_qname}")

        # Extract file name from source_qname
        file_name = source_qname.split(':')[0]

        # First, try to find the type symbol in the same file
        expected_type_qname = f"{file_name}:{type_name}"
        type_symbols = reader.find_symbols(qname=expected_type_qname, language=self.language)
        if type_symbols:
            self.logger.log(self.__class__.__name__,
                          f"DEBUG: Found type symbol in same file: {type_symbols[0]['qname']}")
            return type_symbols[0]

        # If not found in the same file, search across all files (for imported types)
        # This handles the case where types are defined in header files
        all_type_symbols = reader.find_symbols(name=type_name, language=self.language)
        if all_type_symbols:
            # Find the first symbol that matches the type name
            for symbol in all_type_symbols:
                if symbol['name'] == type_name:
                    self.logger.log(self.__class__.__name__,
                                  f"DEBUG: Found type symbol in other file: {symbol['qname']}")
                    return symbol

        self.logger.log(self.__class__.__name__,
                      f"DEBUG: Type symbol not found: {type_name}")
        return None

    def _is_filtered_primitive_typedef(self, type_name: str, source_qname: str, reader) -> bool:
        """
        Check if a type name represents a typedef that was filtered out as a primitive alias.

        This handles cases where typedefs like 'typedef int Integer;' are filtered out
        during symbol extraction but still appear in the AST as type identifiers.
        """
        import re

        # Check if the type name matches common primitive typedef patterns
        primitive_typedef_patterns = [
            r'^Integer$',      # typedef int Integer
            r'^String$',       # typedef char* String (if it were defined)
            r'^Boolean$',      # typedef int Boolean
            r'^Float$',        # typedef float Float
            r'^Double$',       # typedef double Double
            # Add more common primitive typedef names as needed
        ]

        for pattern in primitive_typedef_patterns:
            if re.match(pattern, type_name):
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Identified {type_name} as filtered primitive typedef")
                return True

        # Also check against standard C primitive type names that might be typedef'd
        if type_name in ['int', 'char', 'long', 'short', 'float', 'double', 'void', 'bool']:
            return True

        # Check for standard library typedef patterns
        std_patterns = [
            r'^(u?int\d*_t)$',  # uint32_t, int64_t, etc.
            r'^(size_t|ptrdiff_t|time_t)$',  # Standard types
        ]
        for pattern in std_patterns:
            if re.match(pattern, type_name):
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Identified {type_name} as standard library typedef")
                return True

        return False

    def resolve_complex(self, writer, reader):
        """
        Phase 3: Handle complex 'uses' relationship resolution.

        For C, this handles cases where typedefs were filtered out as primitive aliases.
        If a type symbol doesn't exist, it means it was filtered out and the relationship
        should be deleted rather than left unresolved.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: CUsesRelationshipHandler.resolve_complex called")

        # Query unresolved 'uses' relationships for C language
        unresolved = reader.find_unresolved("uses", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved 'uses' relationships in Phase 3")

        deleted_count = 0
        for rel in unresolved:
            self.logger.log(self.__class__.__name__,
                          f"DEBUG: Processing unresolved 'uses' relationship in Phase 3: {rel['source_qname']} -> {rel['target_name']}")

            # Try to resolve the type reference one more time
            target_symbol = self._resolve_type_reference(rel['target_name'], rel['source_qname'], reader)

            if target_symbol:
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Creating resolved 'uses' relationship in Phase 3: {rel['source_qname']} -> {target_symbol['qname']}")
                writer.add_relationship(
                    source_symbol_id=rel['source_symbol_id'],
                    target_symbol_id=target_symbol['id'],
                    rel_type="uses",
                    source_qname=rel['source_qname'],
                    target_qname=target_symbol['qname']
                )
                # Delete the unresolved relationship
                writer.delete_unresolved_relationship(rel['id'])
                self.logger.log(self.__class__.__name__, "DEBUG: 'uses' relationship resolved in Phase 3")
            else:
                # If we still can't resolve it, check if it's a filtered primitive typedef
                if self._is_filtered_primitive_typedef(rel['target_name'], rel['source_qname'], reader):
                    self.logger.log(self.__class__.__name__,
                                  f"DEBUG: Deleting unresolved 'uses' relationship for filtered primitive typedef: {rel['target_name']}")
                    writer.delete_unresolved_relationship(rel['id'])
                    deleted_count += 1
                else:
                    self.logger.log(self.__class__.__name__,
                                  f"DEBUG: Could not resolve 'uses' relationship in Phase 3: {rel['target_name']}")

        self.logger.log(self.__class__.__name__, f"DEBUG: Deleted {deleted_count} filtered primitive typedef relationships in Phase 3")
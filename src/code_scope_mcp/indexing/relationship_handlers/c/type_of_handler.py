from typing import TYPE_CHECKING, Any, Optional, List

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler


class CTypeOfRelationshipHandler(BaseRelationshipHandler):
    """C-specific implementation of type_of relationship handler for typedefs."""

    relationship_type = "type_of"
    phase_dependencies = ["imports"]  # Need type symbols to be available

    def __init__(self, language: str, language_obj, logger):
        super().__init__(language, language_obj, logger)
        self.logger.log(self.__class__.__name__, f"DEBUG: CTypeOfRelationshipHandler initialized for language {language}")

    def extract_from_ast(self, tree: 'Tree', writer, reader, file_qname: str):
        """
        Phase 1: Extract 'type_of' relationships for typedef declarations.

        Finds typedef declarations and creates 'type_of' relationships
        from the typedef symbol to its underlying type symbol.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: CTypeOfRelationshipHandler.extract_from_ast called")

        # Track created relationships to avoid duplicates
        created_relationships = set()

        # Find all typedef declarations
        typedef_query = """
            (type_definition) @typedef
        """

        query = self.language_obj.query(typedef_query)
        captures = query.captures(tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "typedef":
                # Process this typedef to create type_of relationship
                self._process_typedef(node, tree, writer, reader, file_qname, created_relationships)

    def _process_typedef(self, typedef_node, tree, writer, reader, file_qname, created_relationships):
        """Process a typedef node to create type_of relationship."""
        # Extract typedef information
        typedef_info = self._extract_typedef_info(typedef_node)
        if not typedef_info:
            return

        typedef_name = typedef_info['name']
        underlying_type = typedef_info['underlying_type']

        # Only create type_of for interesting typedefs (avoid primitive aliases)
        if not self._is_interesting_typedef(underlying_type):
            return

        # Create type_of relationship from typedef to underlying type
        typedef_qname = f"{file_qname.split(':')[0]}:{typedef_name}"

        # Get typedef symbol ID
        typedef_symbols = reader.find_symbols(qname=typedef_qname, language=self.language)
        if typedef_symbols:
            typedef_symbol_id = typedef_symbols[0]['id']

            # Try to find the underlying type symbol
            underlying_qname = f"{file_qname.split(':')[0]}:{underlying_type}"

            # For struct/enum types, the underlying type might be the struct/enum name
            if underlying_type.startswith('struct ') or underlying_type.startswith('enum '):
                type_name = underlying_type.split(' ', 1)[1]
                underlying_qname = f"{file_qname.split(':')[0]}:{type_name}"

            # Skip if the underlying type is a primitive that won't have a symbol
            if underlying_type in ['int', 'char', 'long', 'short', 'float', 'double', 'void', 'unsigned long', 'unsigned int']:
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Skipping type_of for primitive typedef: {typedef_qname} -> {underlying_type}")
                return

            underlying_symbols = reader.find_symbols(qname=underlying_qname, language=self.language)

            if underlying_symbols:
                underlying_symbol_id = underlying_symbols[0]['id']

                # Avoid duplicate relationships
                relationship_key = f"{typedef_qname}:{underlying_qname}"
                if relationship_key in created_relationships:
                    return
                created_relationships.add(relationship_key)

                # Create type_of relationship
                writer.add_relationship(
                    source_symbol_id=typedef_symbol_id,
                    target_symbol_id=underlying_symbol_id,
                    rel_type="type_of",
                    source_qname=typedef_qname,
                    target_qname=underlying_qname
                )
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Created 'type_of' relationship: {typedef_qname} -> {underlying_qname}")
            else:
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Underlying type symbol not found: {underlying_qname}")
        else:
            self.logger.log(self.__class__.__name__,
                          f"DEBUG: Typedef symbol not found: {typedef_qname}")

    def _extract_typedef_info(self, typedef_node):
        """Extract typedef name and underlying type."""
        # Get the declarator (the new type name)
        declarator = typedef_node.child_by_field_name("declarator")
        if not declarator:
            return None

        name = None
        if declarator.type == "type_identifier":
            name = declarator.text.decode('utf-8')
        elif declarator.type == "pointer_declarator":
            # Handle pointer typedefs like typedef int* IntPtr;
            inner = declarator.child_by_field_name("declarator")
            if inner and inner.type == "type_identifier":
                name = inner.text.decode('utf-8')

        if not name:
            return None

        # Get the underlying type
        type_node = typedef_node.child_by_field_name("type")
        underlying_type = self._get_underlying_type(type_node) if type_node else ""

        return {
            'name': name,
            'underlying_type': underlying_type
        }

    def _get_underlying_type(self, type_node):
        """Get the underlying type string from a type node."""
        if type_node.type == "primitive_type":
            return type_node.text.decode('utf-8')
        elif type_node.type == "struct_specifier":
            # Extract struct name if available
            name_node = type_node.child_by_field_name("name")
            if name_node and name_node.type == "type_identifier":
                return f"struct {name_node.text.decode('utf-8')}"
            else:
                return "struct"  # Anonymous struct
        elif type_node.type == "enum_specifier":
            # Extract enum name if available
            name_node = type_node.child_by_field_name("name")
            if name_node and name_node.type == "type_identifier":
                return f"enum {name_node.text.decode('utf-8')}"
            else:
                return "enum"  # Anonymous enum
        elif type_node.type == "type_identifier":
            return type_node.text.decode('utf-8')
        elif type_node.type == "pointer_type":
            return "pointer"
        elif type_node.type == "function_type":
            return "function"
        else:
            # For complex types, get the text
            return type_node.text.decode('utf-8')[:50]  # Limit length

    def _is_interesting_typedef(self, underlying_type: str) -> bool:
        """Determine if a typedef is interesting enough to track type_of relationship."""
        import re

        # ALWAYS TRACK (high semantic value)
        if underlying_type.startswith('struct ') or underlying_type.startswith('enum '):
            return True  # typedef struct Point Point;
        if '(*' in underlying_type or underlying_type == 'function':
            return True  # Function pointers

        # NEVER TRACK (primitive aliases cause relationship bloat)
        primitive_patterns = [
            r'^(int|char|long|short|float|double|void|bool)$',
            r'^(u?int\d*_t|size_t|ptrdiff_t)$',
        ]
        for pattern in primitive_patterns:
            if re.search(pattern, underlying_type):
                return False  # typedef int Integer; (problematic)

        return True  # Everything else (custom pointers, etc.)

    def resolve_immediate(self, writer, reader):
        """
        Phase 2: No immediate resolution needed for type_of relationships.
        They are resolved during extraction.
        """
        pass

    def resolve_complex(self, writer, reader):
        """
        Phase 3: Handle complex type_of relationship resolution.

        This generic handler doesn't implement complex resolution.
        Language-specific subclasses can override this method if needed.
        """
        pass
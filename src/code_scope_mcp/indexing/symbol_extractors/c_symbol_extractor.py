from pathlib import Path
from typing import List

from ..models import Symbol
from ..writer import IndexWriter
from .base_symbol_extractor import BaseSymbolExtractor, SymbolExtractionContext


class CFunctionExtractor:
    """Handles C function declarations and definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract function symbols and declares_file_function relationships"""
        from tree_sitter import Query

        symbols = []

        # Query for both function definitions and declarations
        function_queries = [
            "(function_definition) @function",
            "(declaration type: (primitive_type) declarator: (function_declarator) @function_decl)",
        ]

        for query_text in function_queries:
            query = context.language_obj.query(query_text)
            captures = query.captures(context.tree.root_node)

            for capture in captures:
                node = capture[0]
                capture_name = capture[1]

                if capture_name in ["function", "function_decl"]:
                    # Get function name - walk the AST to find the identifier
                    name = self._extract_function_name(node)

                    if name:
                        # Create function symbol
                        function_qname = f"{context.file_name}:{name}"
                        symbol = Symbol(
                            name=name,
                            qname=function_qname,
                            symbol_type="function",
                            file_path=context.file_symbol.file_path,
                            line_number=node.start_point[0] + 1,
                            language="c",
                            file_id=context.file_symbol.file_id,
                        )
                        context.writer.add_symbol(symbol)
                        symbols.append(symbol)

                        # Create declares_file_function relationship
                        context.writer.add_relationship(
                            source_symbol_id=context.file_symbol.id,
                            target_symbol_id=symbol.id,
                            rel_type="declares_file_function",
                            source_qname=context.file_qname,
                            target_qname=function_qname,
                        )

        return symbols

    def _extract_function_name(self, function_node):
        """Extract function name from various AST patterns"""
        # Try simple patterns first
        declarator = function_node.child_by_field_name("declarator")
        if declarator:
            if declarator.type == "identifier":
                return declarator.text.decode('utf-8')
            elif declarator.type == "function_declarator":
                # For function declarators, the name is usually a child
                name_child = declarator.child_by_field_name("declarator")
                if name_child and name_child.type == "identifier":
                    return name_child.text.decode('utf-8')

        # Fallback: walk the tree looking for an identifier
        def find_identifier(node):
            if node.type == "identifier":
                return node.text.decode('utf-8')
            for child in node.children:
                result = find_identifier(child)
                if result:
                    return result
            return None

        return find_identifier(function_node)


class CVariableExtractor:
    """Handles C global variable declarations and definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract global variable symbols"""
        from tree_sitter import Query

        symbols = []

        # Query for top-level declaration nodes (excluding function definitions)
        variable_query = """
            (declaration) @declaration
        """

        query = context.language_obj.query(variable_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "declaration":
                # Check if this is at file scope (not inside a function)
                is_global = True
                parent = node.parent
                while parent:
                    if parent.type in ["function_definition", "compound_statement"]:
                        is_global = False
                        break
                    parent = parent.parent

                if is_global:
                    # Extract variable name from declarator
                    self._extract_from_declaration(node, context, symbols)

        return symbols

    def _extract_from_declaration(self, declaration_node, context: SymbolExtractionContext, symbols):
        """Extract variable names from a declaration node"""
        from tree_sitter import Query

        # Query for declarator patterns
        declarator_query = """
            (init_declarator
                declarator: (identifier) @name)
        """

        query = context.language_obj.query(declarator_query)
        captures = query.captures(declaration_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "name":
                name = node.text.decode('utf-8')

                # Create variable symbol
                variable_qname = f"{context.file_name}:{name}"
                symbol = Symbol(
                    name=name,
                    qname=variable_qname,
                    symbol_type="variable",
                    file_path=context.file_symbol.file_path,
                    line_number=declaration_node.start_point[0] + 1,
                    language="c",
                    file_id=context.file_symbol.file_id,
                )
                context.writer.add_symbol(symbol)
                symbols.append(symbol)


class CImportExtractor:
    """Handles C include preprocessor directives - now uses CImportHandler"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Include extraction is handled by CImportHandler in Phase 1"""
        # The CImportHandler will handle all #include directive processing
        return []


class CFunctionCallExtractor:
    """Handles C function call expressions - now uses CFileFunctionCallHandler"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Function call extraction is handled by CFileFunctionCallHandler in Phase 1"""
        # The CFileFunctionCallHandler will handle all function call processing
        return []


class CStructExtractor:
    """Handles C struct definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract struct symbols from AST"""
        from tree_sitter import Query

        symbols = []

        # Query for struct specifiers that have body definitions (not just type references)
        # This avoids extracting struct references used in other declarations
        struct_query = """
            (struct_specifier
                body: (_) @body) @struct
        """

        query = context.language_obj.query(struct_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "struct":
                # Skip if this struct_specifier is part of a typedef
                if self._is_in_typedef(node):
                    continue

                # Extract struct name
                name = self._extract_struct_name(node)
                if name:
                    # Create struct symbol
                    struct_qname = f"{context.file_name}:{name}"
                    symbol = Symbol(
                        name=name,
                        qname=struct_qname,
                        symbol_type="struct",
                        file_path=context.file_symbol.file_path,
                        line_number=node.start_point[0] + 1,
                        language="c",
                        file_id=context.file_symbol.file_id,
                    )
                    context.writer.add_symbol(symbol)
                    symbols.append(symbol)

                    # Create declares_struct relationship
                    context.writer.add_relationship(
                        source_symbol_id=context.file_symbol.id,
                        target_symbol_id=symbol.id,
                        rel_type="declares_struct",
                        source_qname=context.file_qname,
                        target_qname=struct_qname,
                    )

        return symbols

    def _is_in_typedef(self, struct_node):
        """Check if this struct_specifier is part of a typedef declaration"""
        # Walk up the tree to see if we're inside a type_definition (typedef)
        current = struct_node.parent
        while current:
            if current.type == "type_definition":
                return True
            # Stop at function or compound statement boundaries
            if current.type in ["function_definition", "compound_statement"]:
                break
            current = current.parent
        return False

    def _extract_struct_name(self, struct_node):
        """Extract struct name from struct_specifier node"""
        # Look for name field
        name_node = struct_node.child_by_field_name("name")
        if name_node and name_node.type == "type_identifier":
            return name_node.text.decode('utf-8')

        # For anonymous structs in typedefs, we might not have a name
        # but the plan says to handle both named and anonymous
        return None


class CEnumExtractor:
    """Handles C enum definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract enum symbols from AST"""
        from tree_sitter import Query

        symbols = []

        # Query for enum specifiers (both direct definitions and in typedefs)
        enum_query = """
            (enum_specifier) @enum
        """

        query = context.language_obj.query(enum_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "enum":
                # Skip if this enum_specifier is part of a typedef
                if self._is_in_typedef(node):
                    continue

                # Extract enum name
                name = self._extract_enum_name(node)
                if name:
                    # Create enum symbol
                    enum_qname = f"{context.file_name}:{name}"
                    symbol = Symbol(
                        name=name,
                        qname=enum_qname,
                        symbol_type="enum",
                        file_path=context.file_symbol.file_path,
                        line_number=node.start_point[0] + 1,
                        language="c",
                        file_id=context.file_symbol.file_id,
                    )
                    context.writer.add_symbol(symbol)
                    symbols.append(symbol)
                    
                    # Create declares_enum relationship
                    context.writer.add_relationship(
                        source_symbol_id=context.file_symbol.id,
                        target_symbol_id=symbol.id,
                        rel_type="declares_enum",
                        source_qname=context.file_qname,
                        target_qname=enum_qname,
                    )

        return symbols

    def _is_in_typedef(self, enum_node):
        """Check if this enum_specifier is part of a typedef declaration"""
        # Walk up the tree to see if we're inside a type_definition (typedef)
        current = enum_node.parent
        while current:
            if current.type == "type_definition":
                return True
            # Stop at function or compound statement boundaries
            if current.type in ["function_definition", "compound_statement"]:
                break
            current = current.parent
        return False

    def _extract_enum_name(self, enum_node):
        """Extract enum name from enum_specifier node"""
        # Look for name field
        name_node = enum_node.child_by_field_name("name")
        if name_node and name_node.type == "type_identifier":
            return name_node.text.decode('utf-8')

        # For anonymous enums in typedefs
        return None


class CTypedefExtractor:
    """Handles C typedef declarations with smart filtering"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract typedef symbols from AST with smart filtering"""
        from tree_sitter import Query

        symbols = []

        # Query for typedef declarations
        typedef_query = """
            (type_definition) @typedef
        """

        query = context.language_obj.query(typedef_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "typedef":
                # Extract typedef information
                typedef_info = self._extract_typedef_info(node)
                if typedef_info and self._is_interesting_typedef(typedef_info['type_spec']):
                    name = typedef_info['name']

                    # Create typedef symbol
                    typedef_qname = f"{context.file_name}:{name}"
                    symbol = Symbol(
                        name=name,
                        qname=typedef_qname,
                        symbol_type="typedef",
                        file_path=context.file_symbol.file_path,
                        line_number=node.start_point[0] + 1,
                        language="c",
                        file_id=context.file_symbol.file_id,
                    )
                    context.writer.add_symbol(symbol)
                    symbols.append(symbol)

                    # Create declares_typedef relationship
                    context.writer.add_relationship(
                        source_symbol_id=context.file_symbol.id,
                        target_symbol_id=symbol.id,
                        rel_type="declares_typedef",
                        source_qname=context.file_qname,
                        target_qname=typedef_qname,
                    )

        return symbols

    def _extract_typedef_info(self, typedef_node):
        """Extract typedef name and type specification"""
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

        # Get the type specification
        type_node = typedef_node.child_by_field_name("type")
        type_spec = self._get_type_specification(type_node) if type_node else ""

        return {
            'name': name,
            'type_spec': type_spec
        }

    def _is_interesting_typedef(self, type_spec):
        """Smart filtering to avoid primitive alias explosion"""
        import re

        # ALWAYS TRACK (high semantic value)
        if 'struct' in type_spec or 'enum' in type_spec:
            return True  # typedef struct {...} Point;
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

        return True  # Everything else (custom pointers, etc.)

    def _get_type_specification(self, type_node):
        """Get a string representation of the type for filtering"""
        if type_node.type == "primitive_type":
            return type_node.text.decode('utf-8')
        elif type_node.type == "struct_specifier":
            return "struct"
        elif type_node.type == "enum_specifier":
            return "enum"
        elif type_node.type == "pointer_type":
            return "pointer"
        elif type_node.type == "function_type":
            return "function"
        else:
            # For complex types, get the text
            return type_node.text.decode('utf-8')[:50]  # Limit length



class CSymbolExtractor(BaseSymbolExtractor):
    """Composed C symbol extractor using focused sub-extractors"""

    def __init__(self, file_path: str, language: str, parser, language_obj, logger):
        super().__init__(file_path, language, parser, language_obj, logger)
        self.symbol_extractors = [
            CFunctionExtractor(),
            CVariableExtractor(),
            CStructExtractor(),
            CEnumExtractor(),
            CTypedefExtractor(),
            CImportExtractor(),
            CFunctionCallExtractor(),
        ]

    def extract_symbols(self, tree, writer: IndexWriter, file_qname: str):
        """Extract all symbols using composed sub-extractors"""
        file_qname = self._get_file_qname(self.file_path)

        # Create file symbol
        file_symbol = Symbol(
            name=Path(self.file_path).name,
            qname=file_qname,
            symbol_type="file",
            file_path=self.file_path,
            line_number=0,
            language=self.language,
        )
        writer.add_file_symbol(file_symbol)

        # Create context for sub-extractors
        context = SymbolExtractionContext(
            file_symbol=file_symbol,
            file_qname=file_qname,
            file_name=Path(self.file_path).name,
            writer=writer,
            language_obj=self.language_obj,
            tree=tree,
        )

        # Use sub-extractors to extract all symbols
        all_symbols = []
        for extractor in self.symbol_extractors:
            symbols = extractor.extract_symbols(context)
            all_symbols.extend(symbols)

        return all_symbols

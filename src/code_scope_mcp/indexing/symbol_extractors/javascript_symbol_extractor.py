from pathlib import Path
from typing import List

from ..models import Symbol
from ..writer import IndexWriter
from .base_symbol_extractor import BaseSymbolExtractor, SymbolExtractionContext

class JavascriptClassExtractor:
    """Handles class definitions, inheritance, and class methods"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract class symbols and immediate relationships (declares_class_method, inherits)"""
        from tree_sitter import Query

        symbols = []

        # Query for class_declaration nodes
        class_query = """
            (class_declaration) @class
        """

        query = context.language_obj.query(class_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "class":
                # Get class name
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = name_node.text.decode('utf-8')

                    # Create class symbol
                    class_qname = f"{context.file_name}:{class_name}"
                    class_symbol = Symbol(
                        name=class_name,
                        qname=class_qname,
                        symbol_type="class",
                        file_path=context.file_symbol.file_path,
                        line_number=node.start_point[0] + 1,
                        language="javascript",
                        file_id=context.file_symbol.file_id,
                    )
                    context.writer.add_symbol(class_symbol)
                    symbols.append(class_symbol)

                    # Create declares_class relationship
                    context.writer.add_relationship(
                        source_symbol_id=context.file_symbol.id,
                        target_symbol_id=class_symbol.id,
                        rel_type="declares_class",
                        source_qname=context.file_qname,
                        target_qname=class_qname,
                    )

                    # Extract methods inside the class
                    self._extract_class_methods(node, class_symbol, context, symbols)

                    # Extract inheritance
                    self._extract_inheritance(node, class_symbol, context)

        return symbols

    def _extract_class_methods(self, class_node, class_symbol, context: SymbolExtractionContext, symbols):
        """Extract methods from within a class definition"""
        from tree_sitter import Query

        # Query for method_definition inside the class
        method_query = """
            (method_definition) @method
        """

        query = context.language_obj.query(method_query)
        captures = query.captures(class_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "method":
                # Get method name
                name_node = node.child_by_field_name("name")
                if name_node:
                    method_name = name_node.text.decode('utf-8')

                    # Create method symbol
                    method_qname = f"{class_symbol.name}.{method_name}"
                    method_symbol = Symbol(
                        name=method_name,
                        qname=method_qname,
                        symbol_type="method",
                        file_path=context.file_symbol.file_path,
                        line_number=node.start_point[0] + 1,
                        language="javascript",
                        file_id=context.file_symbol.file_id
                    )
                    context.writer.add_symbol(method_symbol)
                    symbols.append(method_symbol)

                    # Create declares_class_method relationship
                    context.writer.add_relationship(
                        source_symbol_id=class_symbol.id,
                        target_symbol_id=method_symbol.id,
                        rel_type="declares_class_method",
                        source_qname=class_symbol.qname,
                        target_qname=method_qname,
                    )

    def _extract_inheritance(self, class_node, class_symbol, context: SymbolExtractionContext):
        """Extract inheritance relationships"""
        from tree_sitter import Query

        # Query for class heritage (extends clause)
        inheritance_query = """
            (class_heritage
                (identifier) @parent)
        """

        query = context.language_obj.query(inheritance_query)
        captures = query.captures(class_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "parent":
                parent_name = node.text.decode('utf-8')

                # Create unresolved inherits relationship
                # This will be resolved in Phase 2 by relationship handlers
                context.writer.add_unresolved_relationship(
                    source_symbol_id=class_symbol.id,
                    source_qname=class_symbol.qname,
                    target_name=parent_name,
                    rel_type="inherits",
                    needs_type="imports",
                    target_qname=None,  # Will be resolved by handler
                )

class JavascriptFunctionExtractor:
    """Handles standalone function definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract function symbols and declares_file_function relationships"""
        from tree_sitter import Query

        symbols = []

        # Query for function_declaration nodes
        function_query = """
            (function_declaration) @function
        """

        query = context.language_obj.query(function_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "function":
                # Check if this is a module-level function (not inside a class)
                parent = node.parent
                is_module_level = True
                while parent:
                    if parent.type == "class_declaration":
                        is_module_level = False
                        break
                    parent = parent.parent

                if is_module_level:
                    # Get function name
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = name_node.text.decode('utf-8')

                        # Create function symbol
                        function_qname = f"{context.file_name}:{name}"
                        symbol = Symbol(
                            name=name,
                            qname=function_qname,
                            symbol_type="function",
                            file_path=context.file_symbol.file_path,
                            line_number=node.start_point[0] + 1,
                            language="javascript",
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

        # Also handle exported arrow functions (lexical_declaration with arrow function)
        arrow_function_query = """
            (lexical_declaration
                (variable_declarator
                    name: (identifier) @name
                    value: (arrow_function))) @arrow_func
        """

        query = context.language_obj.query(arrow_function_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "arrow_func":
                # Get the variable name
                name_nodes = [child for child in node.children if child.type == "variable_declarator"]
                for var_node in name_nodes:
                    name_node = var_node.child_by_field_name("name")
                    if name_node:
                        name = name_node.text.decode('utf-8')

                        # Create function symbol for arrow function
                        function_qname = f"{context.file_name}:{name}"
                        symbol = Symbol(
                            name=name,
                            qname=function_qname,
                            symbol_type="function",
                            file_path=context.file_symbol.file_path,
                            line_number=node.start_point[0] + 1,
                            language="javascript",
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

class JavascriptConstantExtractor:
    """Handles constant definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract constant symbols"""
        from tree_sitter import Query

        symbols = []

        # Query for lexical_declaration with const keyword
        constant_query = """
            (lexical_declaration
                (variable_declarator
                    name: (identifier) @name
                    value: (_) @value)) @declaration
        """

        query = context.language_obj.query(constant_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "declaration":
                # Check if it's a const declaration
                if b"const" in node.text:
                    # Get the variable name
                    name_nodes = [child for child in node.children if child.type == "variable_declarator"]
                    for var_node in name_nodes:
                        name_node = var_node.child_by_field_name("name")
                        if name_node:
                            name = name_node.text.decode('utf-8')
                            # Check if it matches constant pattern (ALL_CAPS)
                            if name.isupper() and len(name) > 0:
                                # Create constant symbol
                                symbol = Symbol(
                                    name=name,
                                    qname=f"{context.file_name}:{name}",
                                    symbol_type="constant",
                                    file_path=context.file_symbol.file_path,
                                    line_number=node.start_point[0] + 1,
                                    language="javascript",
                                    file_id=context.file_symbol.file_id,
                                )
                                context.writer.add_symbol(symbol)
                                symbols.append(symbol)

                                # Create declares_constant relationship
                                context.writer.add_relationship(
                                    source_symbol_id=context.file_symbol.id,
                                    target_symbol_id=symbol.id,
                                    rel_type="declares_constant",
                                    source_qname=context.file_qname,
                                    target_qname=symbol.qname,
                                )

        return symbols

class JavascriptVariableExtractor:
    """Handles local variable and instance variable definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract local variable and instance variable symbols"""
        symbols = []
        # For now, return empty list as variable extraction is not implemented
        return symbols

class JavascriptImportExtractor:
    """Handles import statements"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract import symbols - import relationships are handled by relationship handlers in Phase 2"""
        # Import relationships are handled by relationship handlers in Phase 2, not during symbol extraction
        # This follows the same pattern as the Python implementation
        return []

class JavascriptSymbolExtractor(BaseSymbolExtractor):
    """Composed symbol extractor using focused sub-extractors"""

    def __init__(self, file_path: str, language: str, parser, language_obj, logger):
        super().__init__(file_path, language, parser, language_obj, logger)
        self.symbol_extractors = [
            JavascriptClassExtractor(),
            JavascriptFunctionExtractor(),
            JavascriptConstantExtractor(),
            JavascriptVariableExtractor(),
            JavascriptImportExtractor(),
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

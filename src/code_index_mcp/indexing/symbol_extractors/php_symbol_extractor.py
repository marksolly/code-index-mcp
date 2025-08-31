from pathlib import Path
from typing import List

from ..models import Symbol
from ..writer import IndexWriter
from .base_symbol_extractor import BaseSymbolExtractor, SymbolExtractionContext

class PhpClassExtractor:
    """Handles class definitions, inheritance, and class methods"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract class symbols and immediate relationships (declares_class_method, inherits)"""
        from tree_sitter import Query

        symbols = []

        # Query for class_declaration nodes using correct tree-sitter PHP syntax
        class_query = """
            (class_declaration
                name: (name) @name) @class
        """

        query = context.language_obj.query(class_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "name":
                class_name = node.text.decode('utf-8')

                # Create class symbol
                class_qname = f"{context.file_name}:{class_name}"
                class_symbol = Symbol(
                    name=class_name,
                    qname=class_qname,
                    symbol_type="class",
                    file_path=context.file_symbol.file_path,
                    line_number=node.start_point[0] + 1,
                    language="php",
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
                self._extract_class_methods(node.parent, class_symbol, context, symbols)

                # Extract properties inside the class
                self._extract_class_properties(node.parent, class_symbol, context, symbols)

                # Extract inheritance relationships
                self._extract_inheritance(node.parent, class_symbol, context)

        return symbols

    def _extract_class_methods(self, class_node, class_symbol, context: SymbolExtractionContext, symbols):
        """Extract methods from within a class definition"""
        from tree_sitter import Query

        # Query for method_declaration inside the class using correct PHP syntax
        method_query = """
            (method_declaration
                name: (name) @name) @method
        """

        query = context.language_obj.query(method_query)
        captures = query.captures(class_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "name":
                method_name = node.text.decode('utf-8')

                # Create method symbol
                method_qname = f"{class_symbol.name}.{method_name}"
                method_symbol = Symbol(
                    name=method_name,
                    qname=method_qname,
                    symbol_type="method",
                    file_path=context.file_symbol.file_path,
                    line_number=node.start_point[0] + 1,
                    language="php",
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

    def _extract_class_properties(self, class_node, class_symbol, context: SymbolExtractionContext, symbols):
        """Extract properties from within a class definition"""
        from tree_sitter import Query

        # Query for property_declaration inside the class using pattern from tags.scm
        property_query = """
            (property_declaration
                (property_element
                    (variable_name (name) @name)
                )
            ) @property
        """

        query = context.language_obj.query(property_query)
        captures = query.captures(class_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "name":
                property_name = node.text.decode('utf-8')

                # Remove $ prefix if present
                if property_name.startswith('$'):
                    property_name = property_name[1:]

                # Create property symbol
                property_qname = f"{class_symbol.name}.{property_name}"
                property_symbol = Symbol(
                    name=property_name,
                    qname=property_qname,
                    symbol_type="variable",  # Using 'variable' as symbol type for properties (supported in PHP language definition)
                    file_path=context.file_symbol.file_path,
                    line_number=node.start_point[0] + 1,
                    language="php",
                    file_id=context.file_symbol.file_id
                )
                context.writer.add_symbol(property_symbol)
                symbols.append(property_symbol)

                # Create declares_class_field relationship (if this relationship type exists)
                # For now, we'll just extract the symbol without a specific relationship
                # The test framework might expect this symbol to exist for is_instance_of relationships

    def _extract_inheritance(self, class_node, class_symbol, context: SymbolExtractionContext):
        """Extract inheritance relationships using Tree-sitter queries"""
        from tree_sitter import Query

        # Use Tree-sitter query to find inheritance relationships
        # PHP extends syntax: class Child extends Parent
        # Try different possible node type names for extends
        inheritance_queries = [
            # Try with base_class
            """
                (class_declaration
                    (base_clause
                        [(name) (qualified_name)] @parent_name
                    )
                )
            """,
            # Try with extends directly
            """
                (class_declaration
                    (extends_clause
                        [(name) (qualified_name)] @parent_name
                    )
                )
            """,
            # Try with class_modifier
            """
                (class_declaration
                    (class_modifier
                        [(name) (qualified_name)] @parent_name
                    )
                )
            """
        ]

        for i, inheritance_query in enumerate(inheritance_queries):
            try:
                query = context.language_obj.query(inheritance_query)
                captures = query.captures(class_node)

                for capture in captures:
                    node = capture[0]
                    capture_name = capture[1]

                    if capture_name == "parent_name":
                        parent_name = node.text.decode('utf-8')

                        # Create unresolved inherits relationship
                        # This will be resolved in Phase 2 by relationship handlers
                        context.writer.add_unresolved_relationship(
                            source_symbol_id=class_symbol.id,
                            source_qname=class_symbol.qname,
                            target_name=parent_name,
                            rel_type="inherits",
                            needs_type="declares_class",
                            target_qname=None,  # Will be resolved by handler
                        )
                        return  # Success, exit function

            except NameError as e:
                # Tree-sitter invalid node type error
                if hasattr(self, 'logger'):
                    self.logger.log(self.__class__.__name__, f"Tree-sitter query {i+1} invalid node type for class {class_symbol.name}: {e}")
                continue
            except Exception as e:
                # Log unexpected errors but don't bury them completely
                if hasattr(self, 'logger'):
                    self.logger.log(self.__class__.__name__, f"Unexpected error in Tree-sitter query {i+1} for class {class_symbol.name}: {e}")
                # Re-raise unexpected errors instead of burying them
                raise ValueError(f"Tree-sitter query {i+1} failed for class {class_symbol.name}") from e

        # If all queries failed, try manual fallback
        try:
            if hasattr(self, 'logger'):
                self.logger.log(self.__class__.__name__, f"All Tree-sitter queries failed for inheritance of class {class_symbol.name}, falling back to manual traversal")
            self._extract_inheritance_manual(class_node, class_symbol, context)
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.log(self.__class__.__name__, f"Manual inheritance extraction also failed for class {class_symbol.name}: {e}")
            # Don't bury this - it's our last resort, so re-raise with context
            raise ValueError(f"Could not extract inheritance for class {class_symbol.name}") from e

    def _extract_inheritance_manual(self, class_node, class_symbol, context: SymbolExtractionContext):
        """Fallback manual extraction of inheritance relationships"""
        def find_extends(node):
            """Recursively find extends clauses"""
            if node.type == "class_declaration":
                # Look for extends keyword and parent class name
                for child in node.children:
                    if child.type == "extends":
                        # The next sibling should be the parent class name
                        extends_index = node.children.index(child)
                        if extends_index + 1 < len(node.children):
                            parent_node = node.children[extends_index + 1]
                            if parent_node.type in ["name", "qualified_name"]:
                                parent_name = parent_node.text.decode('utf-8')

                                # Create unresolved inherits relationship
                                context.writer.add_unresolved_relationship(
                                    source_symbol_id=class_symbol.id,
                                    source_qname=class_symbol.qname,
                                    target_name=parent_name,
                                    rel_type="inherits",
                                    needs_type="declares_class",
                                    target_qname=None,  # Will be resolved by handler
                                )
                                break

            # Recursively search child nodes
            for child in node.children:
                find_extends(child)

        # Start searching from the class node
        find_extends(class_node)

class PhpFunctionExtractor:
    """Handles standalone function definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract function symbols and declares_file_function relationships"""
        from tree_sitter import Query

        symbols = []

        # Query for function_definition nodes using correct PHP syntax
        function_query = """
            (function_definition
                name: (name) @name) @function
        """

        query = context.language_obj.query(function_query)
        captures = query.captures(context.tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "name":
                function_name = node.text.decode('utf-8')

                # Check if this is a module-level function (not inside a class)
                parent = node.parent
                is_module_level = True
                while parent:
                    if parent.type == "class_declaration":
                        is_module_level = False
                        break
                    parent = parent.parent

                if is_module_level:
                    # Create function symbol
                    function_qname = f"{context.file_name}:{function_name}"
                    symbol = Symbol(
                        name=function_name,
                        qname=function_qname,
                        symbol_type="function",
                        file_path=context.file_symbol.file_path,
                        line_number=node.start_point[0] + 1,
                        language="php",
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

class PhpConstantExtractor:
    """Handles constant definitions"""

    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract constant symbols"""
        from tree_sitter import Query

        symbols = []

        # Simple approach: look for const declarations and define() calls manually
        # by traversing the AST and finding the relevant nodes

        def find_constants(node):
            """Recursively find constant declarations and define calls"""
            if node.type == "const_declaration":
                # Handle const declarations like: const MY_CONSTANT1 = "...";
                for child in node.children:
                    if child.type == "const_element":
                        # The name is the first child of const_element
                        if len(child.children) > 0:
                            name_node = child.children[0]
                            if name_node.type == "name":
                                name = name_node.text.decode('utf-8')
                                symbol = Symbol(
                                    name=name,
                                    qname=f"{context.file_name}:{name}",
                                    symbol_type="constant",
                                    file_path=context.file_symbol.file_path,
                                    line_number=node.start_point[0] + 1,
                                    language="php",
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

            elif node.type == "expression_statement":
                # Handle define() calls within expression statements
                for child in node.children:
                    if child.type == "function_call_expression":
                        function_node = child.child_by_field_name("function")
                        if function_node and function_node.text.decode('utf-8') == "define":
                            args = child.child_by_field_name("arguments")
                            if args:
                                # Get arguments as a list
                                arg_list = []
                                for arg_child in args.children:
                                    if arg_child.type == "argument":
                                        # The argument node directly contains the string node
                                        if len(arg_child.children) > 0:
                                            string_node = arg_child.children[0]
                                            if string_node.type == "encapsed_string":
                                                # Extract string content
                                                for string_child in string_node.children:
                                                    if string_child.type == "string_value":
                                                        text = string_child.text.decode('utf-8')
                                                        arg_list.append(text)
                                                        break
                                            elif string_node.type == "string":
                                                # Handle simple string literals
                                                text = string_node.text.decode('utf-8')
                                                # Remove quotes if present
                                                if text.startswith('"') and text.endswith('"'):
                                                    text = text[1:-1]
                                                elif text.startswith("'") and text.endswith("'"):
                                                    text = text[1:-1]
                                                arg_list.append(text)

                                if len(arg_list) >= 1:
                                    name = arg_list[0]
                                    symbol = Symbol(
                                        name=name,
                                        qname=f"{context.file_name}:{name}",
                                        symbol_type="constant",
                                        file_path=context.file_symbol.file_path,
                                        line_number=node.start_point[0] + 1,
                                        language="php",
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

            # Recursively search child nodes
            for child in node.children:
                find_constants(child)

        # Start searching from the root
        find_constants(context.tree.root_node)

        return symbols

class PhpSymbolExtractor(BaseSymbolExtractor):
    """Composed symbol extractor using focused sub-extractors"""

    def __init__(self, file_path: str, language: str, parser, language_obj, logger):
        super().__init__(file_path, language, parser, language_obj, logger)
        self.symbol_extractors = [
            PhpClassExtractor(),
            PhpFunctionExtractor(),
            PhpConstantExtractor(),
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

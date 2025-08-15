import os
from tree_sitter import Language, Parser, Node
from tree_sitter_languages import get_language, get_parser
from .base_analyzer import BaseAnalyzer
from ..indexing.models import FunctionInfo, ClassInfo, ImportInfo, CallInfo, PropertyInfo, VariableInfo, DebugOptions
import re
from typing import List, Dict, Any, Optional

def _debug_symbol(debug_options: DebugOptions, symbol_name: str, language_name: str, node: Node, message: str):
    if (debug_options and
        debug_options.symbol_names and
        any(s in symbol_name for s in debug_options.symbol_names)):
        print(f"DEBUG: [{language_name}] {symbol_name} -> {message}")
        print(f"  Node: {node.type} at {node.start_point}-{node.end_point}")
        print(f"  Text: {node.text.decode('utf-8')[:100]}")


# Language-specific queries for symbol extraction
LANGUAGE_QUERIES = {
    "javascript": {
        "imports": "(import_statement) @import",
        "classes": """
            (class_declaration) @class
            (export_statement (class_declaration) @class)
        """,
        "functions": """
            (function_declaration) @function
            (arrow_function) @function
            (method_definition) @function
        """,
        "methods": "(method_definition) @method",
        "calls": """
            (call_expression) @call
            (new_expression) @call
        """,
        "assignments": "(assignment_expression) @assignment",
    },
    "python": {
        "imports": """
            (import_statement) @import
            (import_from_statement) @import
        """,
        "classes": "(class_definition) @class",
        "functions": "(function_definition) @function",
        "calls": "(call) @call",
        "assignments": "(assignment) @assignment",
        "variable_references": """
            (
                [((identifier) @constant_read)]
                (#match? @constant_read "^[A-Z_][A-Z0-9_]*$")
            )
        """,
    },
    "typescript": {
        "imports": "(import_statement) @import",
        "classes": """
            (class_declaration) @class
            (export_statement (class_declaration) @class)
        """,
        "functions": """
            (function_declaration) @function
            (arrow_function) @function
            (method_definition) @function
        """,
        "methods": "(method_definition) @method",
        "calls": """
            (call_expression) @call
            (new_expression) @call
        """,
    },
    "php": {
        "imports": "(namespace_use_clause) @import",
        "classes": "(class_declaration) @class",
        "functions": "(function_definition) @function",
        "methods": "(method_declaration) @method",
        "calls": "(function_call_expression) @call",
        "namespaces": "(namespace_definition) @namespace",
    },
    "cpp": {
        "imports": "(preproc_include) @import",
        "classes": "(class_specifier) @class",
        "structs": "(struct_specifier) @class",
        "functions": "(function_definition) @function",
        "calls": "(call_expression) @call",
        "namespaces": "(namespace_definition) @namespace",
    },
    "c_sharp": {
        "imports": "(using_directive) @import",
        "classes": "(class_declaration) @class",
        "structs": "(struct_declaration) @class",
        "functions": "(method_declaration) @function",
        "calls": "(invocation_expression) @call",
        "namespaces": "(namespace_declaration) @namespace",
    },
}


class TreeSitterAnalyzer(BaseAnalyzer):
    def __init__(self, language_name: str, debug_options: Optional[DebugOptions] = None):
        self.language_name = language_name
        self.language = get_language(language_name)
        self.parser = get_parser(language_name)
        self.queries = LANGUAGE_QUERIES.get(language_name, {})
        self.file_path = ""
        self.debug_options = debug_options or DebugOptions()
        if self.debug_options.language and self.debug_options.language != self.language_name:
            self.debug_options = DebugOptions() # Reset if language doesn't match
        
        if self.debug_options.symbol_names and self.debug_options.language:
            print(f"DEBUG: TreeSitterAnalyzer for {language_name} initialized with debug symbols: '{self.debug_options.symbol_names}' and language: '{self.debug_options.language}'")

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        self.file_path = file_path
        with open(file_path, "rb") as f:
            source_code = f.read()
        tree = self.parser.parse(source_code)

        imports = self._execute_query(tree, "imports", self._extract_import_info)
        
        all_funcs = []
        all_classes = []

        class_nodes = self._execute_query(tree, "classes", lambda node: node)
        func_nodes = self._execute_query(tree, "functions", lambda node: node)

        for c_node in class_nodes:
            class_info = self._extract_class_info(c_node, [], tree)
            methods = []
            for f_node in func_nodes:
                if self._is_method(f_node, c_node):
                    methods.append(self._extract_function_info(f_node, tree, class_name=class_info.name, imports=imports))
            
            class_info.methods = methods
            all_classes.append(class_info)

        # Extract top-level functions
        for f_node in func_nodes:
            if not self._is_method_of_any_class(f_node, class_nodes):
                all_funcs.append(self._extract_function_info(f_node, tree, imports=imports))

        all_vars = self._execute_query(tree, "assignments", self._extract_variable_info)

        return {
            "functions": all_funcs,
            "classes": all_classes,
            "imports": imports,
            "variables": all_vars,
            "language_specific": {},
        }

    def _is_method(self, func_node: Node, class_node: Node) -> bool:
        return class_node.start_byte <= func_node.start_byte and class_node.end_byte >= func_node.end_byte

    def _is_method_of_any_class(self, func_node: Node, class_nodes: List[Node]) -> bool:
        for c_node in class_nodes:
            if self._is_method(func_node, c_node):
                return True
        return False

    def _execute_query(self, tree, query_name: str, extractor, **kwargs):
        results = []
        query_str = self.queries.get(query_name)
        if not query_str:
            return results

        try:
            query = self.language.query(query_str)
            root_node = kwargs.get('root_node', tree.root_node)
            captures = query.captures(root_node)
            
            nodes_seen = set()
            for node, _ in captures:
                if node.id in nodes_seen:
                    continue
                nodes_seen.add(node.id)
                
                result = extractor(node, **kwargs)
                if result:
                    results.append(result)
        except Exception as e:
            print(f"Error executing query '{query_name}' for {self.language_name}: {e}")

        return results

    def _get_node_text(self, node: Node) -> str:
        return node.text.decode("utf-8") if node else ""

    def _extract_name(self, node: Node) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._get_node_text(name_node)
        
        if self.language_name in ['javascript', 'typescript'] and node.parent and node.parent.type == 'variable_declarator':
            name_node = node.parent.child_by_field_name('name')
            if name_node:
                return self._get_node_text(name_node)

        return "anonymous"

    def _extract_qname(self, node: Node, name: str, imports: Optional[List[ImportInfo]] = None) -> str:
        """Extracts the qualified name for a symbol by traversing up the AST."""
        
        # Check if the name is an imported symbol
        if imports:
            for imp in imports:
                if name in imp.imported_names:
                    if imp.import_type == 'from':
                        if imp.module.startswith('.'):
                            # For 'from .module import name', resolve to module_name.py:name
                            resolved_module_name = imp.module.lstrip('.') + ".py"
                            return f"{resolved_module_name}:{name}"
                        else:
                            # For 'from module import name', use module:name
                            return f"{imp.module}:{name}"
                    elif imp.import_type == 'import':
                        # For 'import module', if 'name' is the module itself, or an alias
                        # This case is less common for direct variable references like constants
                        # but if it happens, we'll use module:name
                        return f"{imp.module}:{name}"

        path_parts = [name]
        
        # Define scope types that contribute to the qname
        scope_types = {
            "php": ["class_declaration", "function_definition", "namespace_definition"],
            "python": ["class_definition", "function_definition"],
            "javascript": ["class_declaration", "function_declaration", "arrow_function"],
            "typescript": ["class_declaration", "function_declaration", "arrow_function"],
            "cpp": ["class_specifier", "struct_specifier", "function_definition", "namespace_definition"],
            "c_sharp": ["class_declaration", "struct_declaration", "method_declaration", "namespace_declaration"],
        }

        # Define separators for different languages
        separators = {
            "php": "\\",
            "cpp": "::",
        }
        separator = separators.get(self.language_name, ".")

        current = node.parent
        while current:
            lang_scope_types = scope_types.get(self.language_name, [])
            if current.type in lang_scope_types:
                scope_name = self._extract_name(current)
                if scope_name != "anonymous":
                    path_parts.append(scope_name)
            current = current.parent
        
        path_parts.reverse()
        
        if len(path_parts) > 1:
            return separator.join(path_parts)
        else:
            # Fallback to file-based qname if no enclosing scope is found
            return f"{os.path.basename(self.file_path)}:{name}"

    def _extract_function_info(self, node: Node, tree, class_name: Optional[str] = None, variable_definitions_map: Optional[Dict[str, VariableInfo]] = None, imports: Optional[List[ImportInfo]] = None) -> FunctionInfo:
        name = self._extract_name(node)
        qname = self._extract_qname(node, name, imports=imports)

        _debug_symbol(self.debug_options, name, self.language_name, node, f"Extracting function info (class context: {class_name})")
        if class_name:
            _debug_symbol(self.debug_options, class_name, self.language_name, node, f"Extracting method '{name}' for class '{class_name}'")
        
        params_node = node.child_by_field_name("parameters")
        parameters = self._get_node_text(params_node).strip("()").split(",") if params_node else []
        parameters = [p.strip() for p in parameters if p.strip()]

        body_node = node.child_by_field_name("body")
        calls = []
        variable_references = []
        if body_node:
            call_nodes = self._execute_query(tree, "calls", lambda n, **kw: n, root_node=body_node)
            for call_node in call_nodes:
                call_info = self._extract_call_info(call_node, class_name)
                if call_info:
                    calls.append(call_info)

            if self.language_name == 'python':
                identifier_nodes = self._execute_query(tree, "variable_references", lambda n, **kw: n, root_node=body_node)
                for id_node in identifier_nodes:
                    id_text = self._get_node_text(id_node)
                    _debug_symbol(self.debug_options, id_text, self.language_name, id_node, f"Captured variable reference: {id_text} (Node Type: {id_node.type})")
                    # Create a VariableInfo object for the reference
                    var_ref_info = VariableInfo(
                        name=id_text,
                        qname=self._extract_qname(id_node, id_text, imports=imports), # Pass imports to _extract_qname
                        line_start=id_node.start_point[0] + 1,
                        line_end=id_node.end_point[0] + 1,
                        line_count=id_node.end_point[0] - id_node.start_point[0] + 1,
                    )
                    variable_references.append(var_ref_info)

        return FunctionInfo(
            name=name,
            qname=qname,
            parameters=parameters,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            line_count=node.end_point[0] - node.start_point[0] + 1,
            calls=calls,
            variable_references=variable_references,
        )

    def _extract_variable_info(self, node: Node) -> Optional[VariableInfo]:
        if self.language_name not in ['python']:
            return None
        
        left_node = node.child_by_field_name('left')
        if not left_node:
            return None

        name = self._get_node_text(left_node)
        
        # Check if it's a top-level constant definition
        is_top_level_constant = (
            node.parent and 
            (node.parent.type == 'module' or node.parent.type == 'decorated_definition') and
            re.match(r"^[A-Z_][A-Z0-9_]*$", name)
        )

        if is_top_level_constant:
            # For top-level constants, simplify qname to just file_name:name
            qname = f"{os.path.basename(self.file_path)}:{name}"
        else:
            qname = self._extract_qname(node, name)

        _debug_symbol(self.debug_options, name, self.language_name, node, "Extracting variable info")

        return VariableInfo(
            name=name,
            qname=qname,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            line_count=node.end_point[0] - node.start_point[0] + 1,
        )

    def _extract_property_info(self, node: Node) -> Optional[PropertyInfo]:
        if self.language_name not in ['javascript', 'typescript']:
            return None

        left_node = node.child_by_field_name('left')
        right_node = node.child_by_field_name('right')

        if not left_node or not right_node or left_node.type != 'member_expression':
            return None

        obj_node = left_node.child_by_field_name('object')
        if not obj_node or self._get_node_text(obj_node) != 'this':
            return None

        prop_name_node = left_node.child_by_field_name('property')
        if not prop_name_node:
            return None
        
        prop_name = self._get_node_text(prop_name_node)
        prop_type = None

        _debug_symbol(self.debug_options, prop_name, self.language_name, node, "Extracting property info")

        if right_node.type == 'new_expression':
            constructor_node = right_node.child_by_field_name('constructor')
            if constructor_node:
                prop_type = self._get_node_text(constructor_node)

        return PropertyInfo(
            name=prop_name,
            type_name=prop_type,
            line_number=node.start_point[0] + 1
        )

    def _extract_class_info(self, node: Node, methods: List[FunctionInfo], tree) -> ClassInfo:
        name = self._extract_name(node)
        qname = self._extract_qname(node, name)

        _debug_symbol(self.debug_options, name, self.language_name, node, "Extracting class info")

        properties = []
        if self.language_name in ['javascript', 'typescript']:
            assignment_nodes = self._execute_query(tree, "assignments", lambda n, **kw: n, root_node=node)
            for assign_node in assignment_nodes:
                if node.start_byte <= assign_node.start_byte and node.end_byte >= assign_node.end_byte:
                    prop_info = self._extract_property_info(assign_node)
                    if prop_info:
                        properties.append(prop_info)

        parent_classes = []
        if self.language_name == 'javascript':
            # For javascript, the heritage is not a named field, but a `class_heritage` node
            for child in node.children:
                if child.type == 'class_heritage':
                    heritage_text = self._get_node_text(child)
                    parts = heritage_text.split()
                    if len(parts) > 1:
                        parent_classes.append(parts[1])
                    else:
                        parent_classes.append(heritage_text)
                    break
        elif self.language_name == 'typescript':
            heritage_node = node.child_by_field_name('heritage')
            if heritage_node:
                for child in heritage_node.children:
                    if child.type == 'extends_clause' and child.child_count > 0:
                        parent_classes.append(self._get_node_text(child.children[0]))
                    elif child.type == 'implements_clause':
                        for type_child in child.children:
                            if type_child.type == 'type_identifier':
                                parent_classes.append(self._get_node_text(type_child))
        elif self.language_name == 'python':
            superclasses_node = node.child_by_field_name('superclasses')
            if superclasses_node:
                for parent in superclasses_node.children:
                    if parent.type in ['identifier', 'attribute']:
                        parent_classes.append(self._get_node_text(parent))
        elif self.language_name == 'php':
            base_clause_node = node.child_by_field_name('base')
            if base_clause_node:
                parent_classes.append(self._get_node_text(base_clause_node))
            
            interfaces_node = node.child_by_field_name('interfaces')
            if interfaces_node:
                for interface in interfaces_node.children:
                    if interface.type == 'name':
                        parent_classes.append(self._get_node_text(interface))
        elif self.language_name == 'cpp':
            base_class_clause = node.child_by_field_name('base_class')
            if base_class_clause:
                for child in base_class_clause.children:
                    if child.type == 'type_identifier':
                        parent_classes.append(self._get_node_text(child))
        elif self.language_name == 'c_sharp':
            base_list_node = node.child_by_field_name('base_list')
            if base_list_node:
                for child in base_list_node.children:
                    if child.type == 'identifier':
                        parent_classes.append(self._get_node_text(child))

        return ClassInfo(
            name=name,
            qname=qname,
            methods=methods,
            properties=properties,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            line_count=node.end_point[0] - node.start_point[0] + 1,
            inherits_from=parent_classes,
        )

    def _extract_import_info(self, node: Node) -> ImportInfo:
        if self.language_name in ['javascript', 'typescript']:
            source_node = node.child_by_field_name("source")
            module = self._get_node_text(source_node) if source_node else "unknown"
            imported_names = []
            import_clause = node.child_by_field_name('clause')
            if import_clause:
                for child in import_clause.children:
                    if child.type in ["named_imports", "namespace_import", "default_import"]:
                        imported_names.append(self._get_node_text(child))
            return ImportInfo(
                module=module.strip("'\""),
                imported_names=imported_names,
                import_type="import",
                line_number=node.start_point[0] + 1,
            )
        elif self.language_name == 'python':
            if node.type == 'import_statement':
                module_node = node.child_by_field_name('name')
                return ImportInfo(
                    module=self._get_node_text(module_node),
                    imported_names=[],
                    import_type='import',
                    line_number=node.start_point[0] + 1,
                )
            elif node.type == 'import_from_statement':
                module_node = node.child_by_field_name('module_name')
                names_node = node.child_by_field_name('names')
                imported_names = self._get_node_text(names_node).split(',') if names_node else []
                return ImportInfo(
                    module=self._get_node_text(module_node),
                    imported_names=[name.strip() for name in imported_names],
                    import_type='from',
                    line_number=node.start_point[0] + 1,
                )
        elif self.language_name == 'php':
            # For PHP, 'use' statements are captured.
            # The structure is (namespace_use_clause (name) (namespace_aliasing_clause (name)))
            # We can extract the full 'use' path.
            name_node = node.child_by_field_name('name')
            if name_node:
                return ImportInfo(
                    module=self._get_node_text(name_node),
                    imported_names=[], # Alias can be handled if needed
                    import_type='use',
                    line_number=node.start_point[0] + 1,
                )
        elif self.language_name == 'cpp':
            path_node = node.child_by_field_name('path')
            if path_node:
                return ImportInfo(
                    module=self._get_node_text(path_node),
                    imported_names=[],
                    import_type='include',
                    line_number=node.start_point[0] + 1,
                )
        elif self.language_name == 'c_sharp':
            name_node = node.child_by_field_name('name')
            if name_node:
                return ImportInfo(
                    module=self._get_node_text(name_node),
                    imported_names=[],
                    import_type='using',
                    line_number=node.start_point[0] + 1,
                )
        return None

    def _extract_call_info(self, node: Node, class_name: Optional[str]) -> Optional[CallInfo]:
        if self.language_name == 'python':
            function_node = node.child_by_field_name('function')
            if not function_node:
                return None

            call_name = ""
            qname = None

            if function_node.type == 'identifier':
                call_name = self._get_node_text(function_node)
            elif function_node.type == 'attribute':
                call_name = self._get_node_text(function_node)
                object_node = function_node.child_by_field_name('object')
                attribute_node = function_node.child_by_field_name('attribute')
                
                if object_node and attribute_node:
                    object_name = self._get_node_text(object_node)
                    
                    if class_name and object_name == 'self':
                        call_name = self._get_node_text(attribute_node)
                        qname = f"{class_name}.{call_name}"

            if call_name:
                return CallInfo(name=call_name, qname=qname)

        elif self.language_name in ['javascript', 'typescript']:
            if node.type == 'new_expression':
                constructor_node = node.child_by_field_name('constructor')
                if constructor_node:
                    call_name = self._get_node_text(constructor_node)
                    return CallInfo(name=call_name, qname=call_name)
                return None

            # This is a call_expression
            function_node = node.child_by_field_name('function')
            if not function_node:
                return None

            call_name = self._get_node_text(function_node)
            qname = None

            if function_node.type == 'member_expression':
                # Handle nested member expressions like `this.engine.start_engine`
                obj = function_node.child_by_field_name('object')
                prop = function_node.child_by_field_name('property')
                
                if obj and prop:
                    obj_text = self._get_node_text(obj)
                    prop_text = self._get_node_text(prop)

                    if class_name and obj_text == 'this':
                        call_name = prop_text
                        qname = f"{class_name}.{prop_text}"
                    elif obj.type == 'member_expression' and self._get_node_text(obj.child_by_field_name('object')) == 'this':
                        # this.engine.start_engine
                        inner_prop = obj.child_by_field_name('property')
                        if inner_prop:
                            inner_prop_text = self._get_node_text(inner_prop)
                            call_name = f"{inner_prop_text}.{prop_text}"
                            # qname is not fully resolved here, but we have the info needed for the resolver
                    else:
                        call_name = f"{obj_text}.{prop_text}"
            
            return CallInfo(name=call_name, qname=qname)

        return None
        return None

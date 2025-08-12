import os
from tree_sitter import Language, Parser, Node
from tree_sitter_languages import get_language, get_parser
from .base_analyzer import BaseAnalyzer
from ..indexing.models import FunctionInfo, ClassInfo, ImportInfo
from typing import List, Dict, Any, Optional

# Language-specific queries for symbol extraction
LANGUAGE_QUERIES = {
    "javascript": {
        "imports": "(import_statement) @import",
        "classes": "(class_declaration) @class",
        "functions": """
            (function_declaration) @function
            (arrow_function) @function
            (method_definition) @function
        """,
        "methods": "(method_definition) @method",
        "calls": "(call_expression) @call",
    },
    "python": {
        "imports": """
            (import_statement) @import
            (import_from_statement) @import
        """,
        "classes": "(class_definition) @class",
        "functions": "(function_definition) @function",
        "calls": """
            (call
                function: (identifier) @call
            )
            (call
                function: (attribute attribute: (identifier) @call)
            )
        """,
    },
    "typescript": {
        "imports": "(import_statement) @import",
        "classes": "(class_declaration) @class",
        "functions": """
            (function_declaration) @function
            (arrow_function) @function
            (method_definition) @function
        """,
        "methods": "(method_definition) @method",
        "calls": "(call_expression) @call",
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
    def __init__(self, language_name: str):
        self.language_name = language_name
        self.language = get_language(language_name)
        self.parser = get_parser(language_name)
        self.queries = LANGUAGE_QUERIES.get(language_name, {})
        self.file_path = ""

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
            methods = []
            for f_node in func_nodes:
                if self._is_method(f_node, c_node):
                    methods.append(self._extract_function_info(f_node, tree))
            
            all_classes.append(self._extract_class_info(c_node, methods))

        # Extract top-level functions
        for f_node in func_nodes:
            if not self._is_method_of_any_class(f_node, class_nodes):
                all_funcs.append(self._extract_function_info(f_node, tree))

        return {
            "functions": all_funcs,
            "classes": all_classes,
            "imports": imports,
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
            captures = query.captures(tree.root_node)
            
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

    def _extract_qname(self, node: Node, name: str) -> str:
        """Extracts the qualified name for a symbol by traversing up the AST."""
        
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

    def _extract_function_info(self, node: Node, tree) -> FunctionInfo:
        name = self._extract_name(node)
        qname = self._extract_qname(node, name)
        
        params_node = node.child_by_field_name("parameters")
        parameters = self._get_node_text(params_node).strip("()").split(",") if params_node else []
        parameters = [p.strip() for p in parameters if p.strip()]

        body_node = node.child_by_field_name("body")
        calls = []
        if body_node:
            call_nodes = self._execute_query(tree, "calls", lambda n, **kw: n, root_node=body_node)
            for call_node in call_nodes:
                if body_node.start_byte <= call_node.start_byte and body_node.end_byte >= call_node.end_byte:
                    calls.append(self._extract_call_info(call_node))

        return FunctionInfo(
            name=name,
            qname=qname,
            parameters=parameters,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            line_count=node.end_point[0] - node.start_point[0] + 1,
            calls=calls,
        )

    def _extract_class_info(self, node: Node, methods: List[FunctionInfo]) -> ClassInfo:
        name = self._extract_name(node)
        qname = self._extract_qname(node, name)

        parent_classes = []
        if self.language_name == 'javascript':
            heritage_node = node.child_by_field_name('heritage')
            if heritage_node:
                parent_classes.append(self._get_node_text(heritage_node))
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

    def _extract_call_info(self, node: Node) -> str:
        return self._get_node_text(node)

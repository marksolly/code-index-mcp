import re
from pathlib import Path

from ..models import Symbol
from ..writer import IndexWriter
from .base import BaseSymbolExtractor


class PythonSymbolExtractor(BaseSymbolExtractor):
    def __init__(self, file_path: str, language: str, logger):
        super().__init__(file_path, language, logger)
        self.queries = {
            "imports": """
                (import_statement) @import
                (import_from_statement) @import
            """,
            "classes": "(class_definition name: (identifier) @name) @class",
            "functions": "(function_definition name: (identifier) @name) @function",
            "calls": "(call) @call",
            "assignments": "(assignment left: _ @name right: _ @value) @assignment",
            "constants": "(assignment left: (identifier) @name) @assignment",
            "constant_references": """
                (
                    [((identifier) @constant_read)]
                    (#match? @constant_read "^[A-Z_][A-Z0-9_]*$")
                )
            """,
        }

    def extract_symbols(self, source_code: str, writer: IndexWriter):
        tree = self.parser.parse(bytes(source_code, "utf8"))
        file_qname = self._get_file_qname(self.file_path)

        writer.add_symbol(Symbol(
            name=Path(self.file_path).name,
            qname=file_qname,
            symbol_type="file",
            file_path=self.file_path,
            line_number=0,
            language=self.language,
        ))

        # We need to process captures for the entire file at once to build scopes correctly
        all_captures = []
        for query_string in self.queries.values():
            query = self.language_obj.query(query_string)
            all_captures.extend(query.captures(tree.root_node))

        processed_nodes = set()
        for node, capture_name in all_captures:
            if node in processed_nodes:
                continue

            # Use the node's type to decide how to handle it, not a loop key
            node_type = node.type
            if node_type == 'import_statement' or node_type == 'import_from_statement':
                self._handle_import(node, all_captures, file_qname, writer)
            elif node_type == 'class_definition':
                self._handle_definition(node, all_captures, file_qname, writer)
            elif node_type == 'function_definition':
                self._handle_definition(node, all_captures, file_qname, writer)
            elif node_type == 'call':
                self._handle_call(node, all_captures, file_qname, writer)
            elif node_type == 'assignment' and capture_name == 'assignment':
                self._handle_instantiation(node, all_captures, file_qname, writer)
                self._handle_constant_definition(node, all_captures, file_qname, writer)
            elif capture_name == 'constant_read':
                 self._handle_constant_reference(node, all_captures, file_qname, writer)

            processed_nodes.add(node)

    def _handle_import(self, node, captures, file_qname, writer: IndexWriter):
        if node.type == 'import_statement':
            for name_node in node.children_by_field_name('name'):
                imported_name = name_node.text.decode()
                writer.add_symbol(Symbol(
                    name=imported_name,
                    qname=f"{file_qname}:{imported_name}",
                    symbol_type="import",
                    file_path=self.file_path,
                    line_number=node.start_point[0],
                    language=self.language,
                ))
                writer.add_unresolved_relationship(
                    source_qname=file_qname,
                    target_name=imported_name,
                    rel_type="imports",
                    needs_type="defines_namespace", # Or file/class/function
                )
        elif node.type == 'import_from_statement':
            module_name_node = node.child_by_field_name('module_name')
            module_name = module_name_node.text.decode() if module_name_node else ''

            for name_node in node.children_by_field_name('name'):
                imported_name = None
                if name_node.type == 'dotted_name':
                    imported_name = name_node.text.decode()
                elif name_node.type == 'aliased_import':
                    name_child = name_node.child_by_field_name('name')
                    if name_child:
                        imported_name = name_child.text.decode()

                if not imported_name:
                    continue

                full_imported_name = f"{module_name}.{imported_name}"
                writer.add_symbol(Symbol(
                    name=imported_name,
                    qname=f"{file_qname}:{imported_name}",
                    symbol_type="import",
                    file_path=self.file_path,
                    line_number=node.start_point[0],
                    language=self.language,
                ))

                # Check if the imported name is a constant
                if re.match(r"^[A-Z_][A-Z0-9_]*$", imported_name):
                    needs_type = "declares_constant"
                else:
                    needs_type = "defines_namespace"

                writer.add_unresolved_relationship(
                    source_qname=file_qname,
                    target_name=imported_name,
                    target_qname=full_imported_name,
                    rel_type="imports",
                    needs_type=needs_type,
                )


    def _handle_definition(self, node, captures, file_qname: str, writer: IndexWriter):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        symbol_name = name_node.text.decode()
        enclosing_scope_qname = self._get_enclosing_scope_qname(node, captures, file_qname)

        if enclosing_scope_qname == file_qname:
            qname = f"{enclosing_scope_qname}:{symbol_name}"
        else:
            qname = f"{enclosing_scope_qname}.{symbol_name}"

        symbol_type = node.type.replace('_definition', '') # 'class' or 'function'

        writer.add_symbol(Symbol(
            name=symbol_name,
            qname=qname,
            symbol_type=symbol_type,
            file_path=self.file_path,
            line_number=node.start_point[0],
            language=self.language,
        ))

        if symbol_type == "function":
            if enclosing_scope_qname == file_qname:
                # Top-level function
                writer.add_unresolved_relationship(
                    source_qname=file_qname,
                    target_name=symbol_name,
                    target_qname=qname,
                    rel_type="declares_file_function",
                    needs_type="declares_file_function",
                )
            elif enclosing_scope_qname:
                # Method within a class
                # The source of the relationship is the class's qname
                source_qname_for_rel = f"{file_qname}:{enclosing_scope_qname}"
                writer.add_unresolved_relationship(
                    source_qname=source_qname_for_rel,
                    target_name=symbol_name,
                    target_qname=qname,
                    rel_type="declares_class_method",
                    needs_type="declares_class_method",
                )

        if symbol_type == "class":
            superclasses_node = node.child_by_field_name("superclasses")
            if superclasses_node:
                for superclass_node in superclasses_node.children:
                    if superclass_node.type in ["identifier", "dotted_name"]:
                        superclass_name = superclass_node.text.decode()
                        writer.add_unresolved_relationship(
                            source_qname=qname,
                            target_name=superclass_name,
                            rel_type="inherits",
                            needs_type="declares_class",
                        )

        # Temporarily remove file_path for cleaner logging
        original_file_path = self.logger.current_context.pop("file_path", None)
        try:
            self.log(
                "Extracted symbol",
                symbol_name=symbol_name,
                qname=qname,
                symbol_type=symbol_type
            )
        finally:
            if original_file_path is not None:
                self.logger.current_context["file_path"] = original_file_path

    def _handle_instantiation(self, node, captures, file_qname: str, writer: IndexWriter):
        name_node = self._find_capture_in_node(captures, node, "name")
        value_node = self._find_capture_in_node(captures, node, "value")

        if not name_node or not value_node:
            return

        # Ensure the value is a class instantiation (a 'call' node)
        if value_node.type != "call":
            return
        value_function_node = value_node.child_by_field_name("function")
        if not value_function_node or value_function_node.type != "identifier":
            return

        class_name = value_function_node.text.decode()
        variable_name = None
        variable_qname = None

        if name_node.type == "attribute":
            object_node = name_node.child_by_field_name("object")
            attribute_node = name_node.child_by_field_name("attribute")
            if object_node and attribute_node and object_node.text.decode() == "self":
                variable_name = attribute_node.text.decode()
                class_qname = self._get_enclosing_class_qname(node, captures, file_qname)
                if not class_qname:
                    return
                
                if ":" in class_qname:
                    enclosing_scope = class_qname.split(":")[-1]
                else:
                    enclosing_scope = class_qname
                variable_qname = f"{enclosing_scope}.{variable_name}"
        elif name_node.type == "identifier":
            variable_name = name_node.text.decode()
            source_qname = self._get_source_qname_for_node(node, file_qname, captures)

            if source_qname == file_qname:
                # Module-level variable
                variable_qname = f"{file_qname}:{variable_name}"
            else:
                # Variable inside a function or method.
                # This is a simplification to avoid creating an invalid 3-part qname.
                # The ideal representation of local variable qnames is not precisely 
                # defined by the developers guide so we assume the standard enclosing_scope.symbol_name format.
                if ":" in source_qname:
                    scope_name = source_qname.split(":")[-1]
                else:  # contains "."
                    scope_name = source_qname.split(".")[-1]

                variable_qname = f"{scope_name}.{variable_name}"

        if not variable_name or not variable_qname:
            return

        # Create a symbol for the variable
        writer.add_symbol(Symbol(
            name=variable_name,
            qname=variable_qname,
            symbol_type="variable",
            file_path=self.file_path,
            line_number=node.start_point[0],
            language=self.language,
        ))

        # Create an unresolved relationship to link the variable to the class
        writer.add_unresolved_relationship(
            source_qname=variable_qname,
            target_name=class_name,
            rel_type="is_instance_of",
            needs_type="declares_class",
        )

        # Also create an 'instantiates' relationship from the enclosing function/method
        source_qname = self._get_source_qname_for_node(node, file_qname, captures)
        if source_qname:
            writer.add_unresolved_relationship(
                source_qname=source_qname,
                target_name=class_name,
                rel_type="instantiates",
                needs_type="declares_class",
            )

    def _handle_call(self, node, captures, file_qname: str, writer: IndexWriter):
        function_node = node.child_by_field_name("function")
        if not function_node:
            return

        target_name = ""
        if function_node.type == "identifier":
            target_name = function_node.text.decode()
        elif function_node.type == "attribute":
            target_node = function_node.child_by_field_name("attribute")
            if target_node:
                target_name = target_node.text.decode()

        if not target_name:
            return

        source_qname = self._get_source_qname_for_node(node, file_qname, captures)

        if function_node.type == "attribute":
            object_node = function_node.child_by_field_name("object")

            if object_node.type == 'identifier' and object_node.text.decode() == 'self':
                self.log("Creating unresolved 'self' call", source_qname=source_qname, target_name=target_name)
                writer.add_unresolved_relationship(
                    source_qname=source_qname,
                    target_name=target_name,
                    rel_type="calls",
                    needs_type="declares_class_method",
                )
                return

            intermediate_symbol_qname = None
            if object_node.type == "attribute":
                # e.g. self.engine in self.engine.start_engine()
                obj_obj_node = object_node.child_by_field_name("object")
                obj_attr_node = object_node.child_by_field_name("attribute")
                if obj_obj_node and obj_attr_node and obj_obj_node.text.decode() == "self":
                    class_qname = self._get_enclosing_class_qname(node, captures, file_qname)
                    if class_qname:
                        instance_variable_name = obj_attr_node.text.decode()
                        if ":" in class_qname:
                            enclosing_scope = class_qname.split(":")[-1]
                        else:
                            enclosing_scope = class_qname
                        intermediate_symbol_qname = f"{enclosing_scope}.{instance_variable_name}"

            if not intermediate_symbol_qname:
                intermediate_symbol_qname = object_node.text.decode()

            writer.add_unresolved_relationship(
                source_qname=source_qname,
                target_name=target_name,
                rel_type="calls",
                needs_type="is_instance_of",
                intermediate_symbol_qname=intermediate_symbol_qname,
            )
        else:
            # This is a direct function call, e.g., my_function()
            # Heuristic: if the target name starts with a capital letter,
            # it's likely a class instantiation.
            if target_name and target_name[0].isupper():
                # This is a class instantiation. Check if it's part of an
                # assignment, which is handled by _handle_assignment.
                if node.parent and node.parent.type == "assignment":
                    return

                rel_type = "instantiates"
                needs_type = "declares_class"
            else:
                rel_type = "calls"
                needs_type = "declares_file_function"

            writer.add_unresolved_relationship(
                source_qname=source_qname,
                target_name=target_name,
                rel_type=rel_type,
                needs_type=needs_type,
            )

    def _handle_constant_definition(self, node, captures, file_qname: str, writer: IndexWriter):
        name_node = node.child_by_field_name("left")
        if not name_node or name_node.type != 'identifier':
            return

        symbol_name = name_node.text.decode()
        if not re.match(r"^[A-Z_][A-Z0-9_]*$", symbol_name):
            return

        # We only care about top-level constants
        if not (node.parent.type == 'expression_statement' and node.parent.parent and node.parent.parent.type == 'module'):
            return

        qname = f"{file_qname}:{symbol_name}"
        writer.add_symbol(Symbol(
            name=symbol_name,
            qname=qname,
            symbol_type="constant",
            file_path=self.file_path,
            line_number=node.start_point[0],
            language=self.language,
        ))
        self.log(
            "Extracted constant",
            symbol_name=symbol_name,
            qname=qname,
            symbol_type="constant",
        )

    def _handle_constant_reference(self, node, captures, file_qname: str, writer: IndexWriter):
        # If this constant is part of an import statement, skip it.
        # It will be handled by the _handle_import method.
        parent = node.parent
        while parent:
            if parent.type in ["import_statement", "import_from_statement"]:
                return
            parent = parent.parent

        target_name = node.text.decode()
        source_qname = self._get_source_qname_for_node(node, file_qname, captures)
        writer.add_unresolved_relationship(
            source_qname=source_qname,
            target_name=target_name,
            rel_type="references_variable",
            needs_type="declares_constant",
        )

    def _get_file_qname(self, file_path: str) -> str:
        return Path(file_path).name

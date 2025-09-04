from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler


class PhpReferencesVariableHandler(BaseRelationshipHandler):
    """Handles PHP variable/constant reference relationships."""

    relationship_type = "references_variable"

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved variable reference relationships from AST.

        PRIMARY PURPOSE: Analyze AST syntax to identify variable references.
        READING FROM DATABASE: Allowed only as last resort for finding source symbol IDs.

        Creates unresolved relationships for variable references.
        """
        # Query for variable and constant references in PHP
        # Look for variable names (starting with $) and constant names
        variable_ref_query = """
            [
              (variable_name
                (name) @variable_ref
              )
              (name) @constant_ref
            ] @reference
        """

        query = self.language_obj.query(variable_ref_query)
        captures = query.captures(tree.root_node)

        # Process each variable reference
        processed_refs = set()

        for node, capture_name in captures:
            if capture_name in ["variable_ref", "constant_ref"]:
                variable_name = node.text.decode('utf-8')

                # Skip if it's part of a declaration (variable being declared)
                if capture_name == "variable_ref" and self._is_variable_declaration(node):
                    continue

                # Skip keywords and built-in functions
                if self._is_keyword_or_builtin(variable_name, node):
                    continue

                # Find the containing method/class context
                source_qname = self._find_containing_context(node, reader, file_qname)

                if source_qname:
                    # Create a unique key for this reference to avoid duplicates
                    ref_key = (source_qname, variable_name)

                    if ref_key not in processed_refs:
                        processed_refs.add(ref_key)
                        self.logger.log(self.__class__.__name__, f"DEBUG: Processing reference: {variable_name} in {source_qname}")

                        # Find source symbol ID
                        source_symbols = reader.find_symbols(qname=source_qname, language=self.language)
                        if source_symbols:
                            source_symbol_id = source_symbols[0]['id']
                            self.logger.log(self.__class__.__name__, f"DEBUG: Creating unresolved relationship: {source_qname} -> {variable_name}")
                            writer.add_unresolved_relationship(
                                source_symbol_id=source_symbol_id,
                                source_qname=source_qname,
                                target_name=variable_name,
                                rel_type="references_variable",
                                needs_type="imports",  # Variables are typically imported
                                target_qname=None
                            )
                        else:
                            self.logger.log(self.__class__.__name__, f"DEBUG: Source symbol not found: {source_qname}")
                    else:
                        self.logger.log(self.__class__.__name__, f"DEBUG: Skipping duplicate reference: {variable_name} in {source_qname}")

    def _is_variable_declaration(self, node) -> bool:
        """Check if a variable reference is part of a variable declaration."""
        current = node.parent
        while current:
            if current.type in ["assignment_expression", "simple_parameter"]:
                # Check if this variable is on the left side of an assignment
                for child in current.children:
                    if child.type == "variable_name" and child == node.parent:
                        # This is the variable being assigned to
                        return True
            elif current.type == "property_declaration":
                # Property declarations in classes
                return True
            current = current.parent
        return False

    def _is_keyword_or_builtin(self, name: str, node) -> bool:
        """Check if a name is a PHP keyword, built-in function, or should be skipped."""
        # PHP keywords
        keywords = {
            'abstract', 'and', 'array', 'as', 'break', 'callable', 'case', 'catch', 'class',
            'clone', 'const', 'continue', 'declare', 'default', 'die', 'do', 'echo', 'else',
            'elseif', 'empty', 'enddeclare', 'endfor', 'endforeach', 'endif', 'endswitch',
            'endwhile', 'eval', 'exit', 'extends', 'final', 'finally', 'fn', 'for', 'foreach',
            'function', 'global', 'goto', 'if', 'implements', 'include', 'include_once',
            'instanceof', 'insteadof', 'interface', 'isset', 'list', 'match', 'namespace',
            'new', 'or', 'print', 'private', 'protected', 'public', 'readonly', 'require',
            'require_once', 'return', 'static', 'switch', 'throw', 'trait', 'try', 'unset',
            'use', 'var', 'while', 'xor', 'yield', 'yield_from', '__halt_compiler',
            '__CLASS__', '__DIR__', '__FILE__', '__FUNCTION__', '__LINE__', '__METHOD__',
            '__NAMESPACE__', '__TRAIT__'
        }

        if name in keywords:
            return True

        # Skip if it's a function declaration (the function name itself)
        current = node.parent
        while current:
            if current.type == "function_definition":
                for child in current.children:
                    if child.type == "name" and child == node:
                        return True
            elif current.type == "method_declaration":
                for child in current.children:
                    if child.type == "name" and child == node:
                        return True
            elif current.type == "class_declaration":
                for child in current.children:
                    if child.type == "name" and child == node:
                        return True
            current = current.parent

        return False

    def _find_containing_context(self, node, reader: 'IndexReader', file_qname: str):
        """
        Find the containing method or function context for a node.

        Args:
            node: The AST node to find context for
            reader: IndexReader instance
            file_qname: The file qname

        Returns:
            Qualified name of containing context, or file_qname if no specific context found
        """
        current = node.parent
        while current:
            if current.type == "method_declaration":
                # Found a method context
                method_name = self._extract_method_name(current)
                class_name = self._find_containing_class(current)

                if method_name and class_name:
                    return f"{class_name}.{method_name}"
                elif method_name:
                    # Method in anonymous class or similar
                    return method_name

            elif current.type == "function_definition":
                # Found a function context
                function_name = self._extract_function_name(current)
                if function_name:
                    # Extract clean filename from file_qname (remove :__FILE__ suffix if present)
                    clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                    return f"{clean_file_name}:{function_name}"

            current = current.parent

        # If no function/method context found, return file context
        return file_qname

    def _extract_method_name(self, method_node) -> str:
        """Extract method name from method declaration node."""
        for child in method_node.children:
            if child.type == 'name':
                return child.text.decode('utf-8')
        return None

    def _extract_function_name(self, function_node) -> str:
        """Extract function name from function definition node."""
        for child in function_node.children:
            if child.type == 'name':
                return child.text.decode('utf-8')
        return None

    def _find_containing_class(self, node) -> str:
        """Find the containing class for a node."""
        current = node.parent
        while current:
            if current.type == "class_declaration":
                for child in current.children:
                    if child.type == 'name':
                        return child.text.decode('utf-8')
            current = current.parent
        return None

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Resolve variable references using import relationships.

        Resolves references by finding imported variables or local variables.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: PhpReferencesVariableHandler.resolve_immediate called")

        # Query unresolved 'references_variable' relationships
        unresolved = reader.find_unresolved("references_variable", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved references_variable relationships")

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Processing unresolved reference: {rel['source_qname']} -> {rel['target_name']}")

            # Try to resolve the variable reference
            target_symbol = self._resolve_variable_reference(rel['target_name'], rel['source_qname'], reader)

            if target_symbol:
                self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved reference: {rel['source_qname']} -> {target_symbol['qname']}")
                # Create resolved relationship
                writer.add_relationship(
                    source_symbol_id=rel['source_symbol_id'],
                    target_symbol_id=target_symbol['id'],
                    rel_type="references_variable",
                    source_qname=rel['source_qname'],
                    target_qname=target_symbol['qname']
                )
                # Delete the unresolved relationship
                writer.delete_unresolved_relationship(rel['id'])
                self.logger.log(self.__class__.__name__, "DEBUG: Variable reference resolved")
            else:
                self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve variable reference: {rel['target_name']}")

    def _resolve_variable_reference(self, variable_name: str, source_qname: str, reader: 'IndexReader'):
        """
        Resolve a variable reference by looking for imported or local variables.

        Args:
            variable_name: The name of the variable being referenced
            source_qname: The qname of the source (method/function/file)
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Resolving variable reference: {variable_name}")

        # First, try to find imported variables
        source_file = source_qname.split(':')[0] + ":__FILE__"
        import_rels = reader.find_relationships(
            source_qname=source_file,
            rel_type="imports",
            source_language=self.language,
            target_language=self.language
        )

        for import_rel in import_rels:
            if import_rel['target_qname'] and import_rel['target_qname'].endswith(f":{variable_name}"):
                target_symbols = reader.find_symbols(qname=import_rel['target_qname'], language=self.language)
                if target_symbols:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Found imported variable: {target_symbols[0]['qname']}")
                    return target_symbols[0]

        # If not found as imported, try to find as local variable in the same file
        source_file_name = source_qname.split(':')[0]
        local_variable_qname = f"{source_file_name}:{variable_name}"
        local_symbols = reader.find_symbols(qname=local_variable_qname, language=self.language)
        if local_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found local variable: {local_symbols[0]['qname']}")
            return local_symbols[0]

        # Try searching by name across all files (fallback)
        target_symbols = reader.find_symbols(name=variable_name, language=self.language)
        # Filter for variable/constant symbols only
        variable_symbols = [s for s in target_symbols if s['symbol_type'] in ['variable', 'constant']]
        if variable_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found variable by name: {variable_symbols[0]['qname']}")
            return variable_symbols[0]

        self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve variable reference: {variable_name}")
        return None

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle complex variable reference resolution.

        For now, this is a no-op as most variable references should be resolved in Phase 2.
        """
        pass

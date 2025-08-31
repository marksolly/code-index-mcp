from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler

class PythonReferencesConstantHandler(BaseRelationshipHandler):
    """Handles Python constant/variable reference relationships."""

    relationship_type = "references_variable"

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved constant reference relationships from AST.

        PRIMARY PURPOSE: Analyze AST syntax to identify constant references (ALL_CAPS identifiers).
        READING FROM DATABASE: Allowed only as last resort for finding source symbol IDs.

        Creates unresolved relationships for constant references.
        """
        from tree_sitter import Query

        # Query for identifier references in assignments and expressions
        # Look for identifiers that are ALL_CAPS (Python constant convention)
        constant_ref_query = """
            [
                (assignment
                    right: (identifier) @constant_ref
                )
                (identifier) @constant_ref
            ]
        """

        query = self.language_obj.query(constant_ref_query)
        captures = query.captures(tree.root_node)

        # Group captures by node for easier processing
        capture_groups = {}
        for node, capture_name in captures:
            if capture_name not in capture_groups:
                capture_groups[capture_name] = []
            capture_groups[capture_name].append(node)

        # Process each constant reference
        constant_nodes = capture_groups.get("constant_ref", [])

        # Deduplicate relationships to avoid creating multiple relationships for the same constant in the same context
        processed_refs = set()

        for constant_node in constant_nodes:
            constant_name = constant_node.text.decode('utf-8')

            # Only process ALL_CAPS identifiers (Python constant convention)
            if constant_name.isupper():
                # Find the containing method/class context
                source_qname = self._find_containing_context(constant_node, reader, file_qname)

                if source_qname:
                    # Create a unique key for this reference to avoid duplicates
                    ref_key = (source_qname, constant_name)

                    if ref_key not in processed_refs:
                        processed_refs.add(ref_key)
                        self.logger.log(self.__class__.__name__, f"DEBUG: Processing constant reference: {constant_name} in {source_qname}")

                        # Find source symbol ID
                        source_symbols = reader.find_symbols(qname=source_qname, language=self.language)
                        if source_symbols:
                            source_symbol_id = source_symbols[0]['id']
                            self.logger.log(self.__class__.__name__, f"DEBUG: Creating unresolved relationship: {source_qname} -> {constant_name}")
                            writer.add_unresolved_relationship(
                                source_symbol_id=source_symbol_id,
                                source_qname=source_qname,
                                target_name=constant_name,
                                rel_type="references_variable",
                                needs_type="imports",  # Constants are typically imported
                                target_qname=None,
                                intermediate_symbol_qname=file_qname
                            )
                        else:
                            self.logger.log(self.__class__.__name__, f"DEBUG: Source symbol not found: {source_qname}")
                    else:
                        self.logger.log(self.__class__.__name__, f"DEBUG: Skipping duplicate constant reference: {constant_name} in {source_qname}")

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
            if current.type == "function_definition":
                # Get function/method name
                for child in current.children:
                    if child.type == "identifier":
                        func_name = child.text.decode('utf-8')

                        # Check if this is a method (inside a class) or standalone function
                        class_name = None
                        parent = current.parent
                        while parent:
                            if parent.type == "class_definition":
                                # Get class name
                                for class_child in parent.children:
                                    if class_child.type == "identifier":
                                        class_name = class_child.text.decode('utf-8')
                                        break
                                break
                            parent = parent.parent

                        if class_name:
                            return f"{class_name}.{func_name}"
                        else:
                            file_name = file_qname.split(':')[0]
                            return f"{file_name}:{func_name}"

            current = current.parent

        # If no function/method context found, return file context
        return file_qname

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Resolve constant references using import relationships.

        Resolves references by finding imported constants or local constants.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: PythonReferencesConstantHandler.resolve_immediate called")

        # Query unresolved 'references_variable' relationships for this language only
        unresolved = reader.find_unresolved("references_variable", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved references_variable relationships for {self.language}")

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Processing unresolved reference: {rel['source_qname']} -> {rel['target_name']}")

            # Try to resolve the constant reference
            target_symbol = self._resolve_constant_reference(rel['target_name'], rel, reader)

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
                self.logger.log(self.__class__.__name__, "DEBUG: Constant reference resolved")
            else:
                self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve constant reference: {rel['target_name']}")

    def _resolve_constant_reference(self, constant_name: str, rel: dict, reader: 'IndexReader'):
        """
        Resolve a constant reference by looking for imported or local constants.

        Args:
            constant_name: The name of the constant being referenced
            rel: The unresolved relationship dict
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Resolving constant reference: {constant_name} from {rel['source_qname']}")

        # Get the file qname from the intermediate_symbol_qname
        source_file = rel['intermediate_symbol_qname']
        self.logger.log(self.__class__.__name__, f"DEBUG: Source file: {source_file}")

        # First, try to find imported constants
        import_rels = reader.find_relationships(
            source_qname=source_file,
            rel_type="imports",
            source_language=self.language,
            target_language=self.language
        )
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(import_rels)} import relationships for {source_file}")

        for import_rel in import_rels:
            self.logger.log(self.__class__.__name__, f"DEBUG: Checking import: {import_rel['target_qname']}")
            if import_rel['target_qname'] and import_rel['target_qname'].endswith(f":{constant_name}"):
                self.logger.log(self.__class__.__name__, f"DEBUG: Import matches constant name: {import_rel['target_qname']}")
                target_symbols = reader.find_symbols(qname=import_rel['target_qname'], language=self.language)
                self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(target_symbols)} symbols for qname {import_rel['target_qname']}")
                if target_symbols:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Found imported constant: {target_symbols[0]['qname']} (type: {target_symbols[0]['symbol_type']})")
                    return target_symbols[0]
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: No symbols found for qname {import_rel['target_qname']}")

        # If not found as imported, try to find as local constant in the same file
        source_file_name = source_file.split(':')[0]
        local_constant_qname = f"{source_file_name}:{constant_name}"
        self.logger.log(self.__class__.__name__, f"DEBUG: Checking for local constant: {local_constant_qname}")
        local_symbols = reader.find_symbols(qname=local_constant_qname, language=self.language)
        if local_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found local constant: {local_symbols[0]['qname']} (type: {local_symbols[0]['symbol_type']})")
            return local_symbols[0]

        # Try searching by name across all files (fallback)
        self.logger.log(self.__class__.__name__, f"DEBUG: Falling back to name search for: {constant_name}")
        target_symbols = reader.find_symbols(name=constant_name, language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Name search found {len(target_symbols)} symbols")
        for symbol in target_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Symbol: {symbol['qname']} (type: {symbol['symbol_type']}, language: {symbol['file_path'].split('.')[-1]})")

        # Filter for constant symbols only
        constant_symbols = [s for s in target_symbols if s['symbol_type'] == 'constant']
        self.logger.log(self.__class__.__name__, f"DEBUG: Filtered to {len(constant_symbols)} constant symbols")
        if constant_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found constant by name: {constant_symbols[0]['qname']} (type: {constant_symbols[0]['symbol_type']})")
            return constant_symbols[0]

        self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve constant reference: {constant_name}")
        return None

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle complex constant reference resolution.

        For now, this is a no-op as most constant references should be resolved in Phase 2.
        """
        pass

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler

class ImportRelationshipHandler(BaseRelationshipHandler):
    """Handles import relationship resolution."""

    relationship_type = "imports"

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved import relationships from AST.

        PRIMARY PURPOSE: Analyze AST syntax to identify import candidates.
        READING FROM DATABASE: Not needed - imports are extracted directly from AST.

        This extracts import statements and creates unresolved relationships
        that will be resolved in Phase 2.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: ImportRelationshipHandler.extract_from_ast called")

        # Get the file symbol ID for this file
        file_symbols = reader.find_symbols(qname=file_qname, language=self.language)
        if not file_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: No file symbol found for {file_qname}")
            return

        file_symbol_id = file_symbols[0]['id']

        # Query for from import statements
        from_import_query = """
            (import_from_statement) @from_import_stmt
        """

        # Extract from imports
        query = self.language_obj.query(from_import_query)
        captures = query.captures(tree.root_node)

        for capture in captures:
            node = capture[0]
            capture_name = capture[1]

            if capture_name == "from_import_stmt":
                # Extract module name from relative_import
                relative_import = node.child_by_field_name("module_name")
                if relative_import:
                    module_name = relative_import.text.decode('utf-8')
                else:
                    # Try relative_import for relative imports
                    relative_import = node.child_by_field_name("relative_import")
                    if relative_import:
                        module_name = relative_import.text.decode('utf-8')
                    else:
                        continue

                # Convert module name to file path (simplified for test cases)
                if module_name.startswith('.'):
                    # Relative import - convert to file path
                    target_file = module_name.replace('.', '/') + '.py'
                    if target_file.startswith('/'):
                        target_file = target_file[1:]
                else:
                    target_file = module_name.replace('.', '/') + '.py'

                # Extract all imported names
                # Find all dotted_name nodes that are direct children of the import_from_statement
                imported_names = []
                for child in node.children:
                    if child.type == "dotted_name":
                        imported_names.append(child.text.decode('utf-8'))

                # Create unresolved import relationships for each imported symbol
                for imported_name in imported_names:
                    writer.add_unresolved_relationship(
                        source_symbol_id=file_symbol_id,
                        source_qname=file_qname,
                        target_name=imported_name,
                        rel_type="imports",
                        needs_type="imports",
                        target_qname=None,
                        intermediate_symbol_qname=f"{target_file}:__FILE__"  # Hint about the source file
                    )
                    self.logger.log(self.__class__.__name__, f"DEBUG: Created unresolved import: {file_qname} -> {imported_name} from {target_file}")

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Resolve import relationships that can be resolved immediately.

        Resolves import relationships by finding the imported symbols.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: ImportRelationshipHandler.resolve_immediate called")

        # Query unresolved 'imports' relationships
        unresolved = reader.find_unresolved("imports")
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved imports relationships")

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Processing unresolved import: {rel['source_qname']} -> {rel['target_name']}")

            # Try to resolve the import relationship
            intermediate_qname = rel['intermediate_symbol_qname'] if 'intermediate_symbol_qname' in rel.keys() and rel['intermediate_symbol_qname'] else None
            target_symbol = self._resolve_import_target(rel['target_name'], intermediate_qname, reader)

            if target_symbol:
                self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved import: {rel['source_qname']} -> {target_symbol['qname']}")
                # Create resolved relationship
                writer.add_relationship(
                    source_symbol_id=rel['source_symbol_id'],
                    target_symbol_id=target_symbol['id'],
                    rel_type="imports",
                    source_qname=rel['source_qname'],
                    target_qname=target_symbol['qname']
                )
                # Delete the unresolved relationship
                writer.delete_unresolved_relationship(rel['id'])
                self.logger.log(self.__class__.__name__, "DEBUG: Import relationship resolved")
            else:
                self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve import target: {rel['target_name']}")

    def _resolve_import_target(self, target_name: str, intermediate_symbol_qname: str, reader: 'IndexReader'):
        """
        Resolve the target of an import relationship.

        Args:
            target_name: The name of the symbol being imported
            intermediate_symbol_qname: Optional hint about the source file
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Resolving import target: {target_name}")

        # If we have an intermediate symbol qname (from from-imports), look there first
        if intermediate_symbol_qname:
            # Look for the symbol in the specified file
            file_name = intermediate_symbol_qname.split(':')[0]
            symbols_in_file = reader.find_symbols(qname=f"{file_name}:{target_name}", language=self.language)
            if symbols_in_file:
                self.logger.log(self.__class__.__name__, f"DEBUG: Found import target in specified file: {symbols_in_file[0]['qname']}")
                return symbols_in_file[0]

        # Otherwise, search for the symbol by name across all files
        target_symbols = reader.find_symbols(name=target_name, language=self.language)
        if target_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found import target by name: {target_symbols[0]['qname']}")
            return target_symbols[0]

        self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve import target: {target_name}")
        return None

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle complex import resolution.

        For now, this is a no-op as most imports should be resolved in Phase 2.
        """
        pass

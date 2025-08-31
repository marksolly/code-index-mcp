from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler


class BaseImportHandler(BaseRelationshipHandler, ABC):
    """Abstract base class for import relationship handlers.

    This class provides the reusable logic for import resolution that works
    across multiple programming languages. Language-specific subclasses only
    need to implement 3 abstract methods to handle their unique AST patterns.

    ## Inheritance Pattern

    To create a new language-specific import handler:

    ```python
    class MyLanguageImportHandler(BaseImportHandler):
        def _get_import_queries(self) -> list[str]:
            # Return tree-sitter queries for your language's import syntax
            return ["(import_statement) @import"]

        def _extract_import_from_node(self, node) -> Optional[dict]:
            # Extract module name and imported symbols from AST node
            # Return {'module_name': str, 'imported_names': list[str]}
            pass

        def _convert_module_to_file_path(self, module_name: str) -> str:
            # Convert module name to file path using language-specific rules
            pass
    ```

    The base class handles all the complex resolution logic including:
    - Finding imported symbols through imports
    - Resolving relative vs absolute imports
    - Managing unresolved relationships
    - Coordinating with the database
    """

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
        self.logger.log(self.__class__.__name__, "DEBUG: BaseImportHandler.extract_from_ast called")

        # Get the file symbol ID for this file
        file_symbols = reader.find_symbols(qname=file_qname, language=self.language)
        if not file_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: No file symbol found for {file_qname}")
            return

        file_symbol_id = file_symbols[0]['id']

        # Get language-specific import queries
        import_queries = self._get_import_queries()

        # Extract imports using language-specific queries
        for query_text in import_queries:
            query = self.language_obj.query(query_text)
            captures = query.captures(tree.root_node)

            for capture in captures:
                node = capture[0]
                capture_name = capture[1]

                if capture_name == "from_import_stmt":
                    # Extract import details using language-specific method
                    import_details = self._extract_import_from_node(node)
                    if not import_details:
                        continue

                    module_name = import_details['module_name']
                    imported_names = import_details['imported_names']

                    # Convert module name to file path using language-specific logic
                    target_file = self._convert_module_to_file_path(module_name)

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

    @abstractmethod
    def _get_import_queries(self) -> list[str]:
        """Return language-specific tree-sitter queries for import statements."""
        pass

    @abstractmethod
    def _extract_import_from_node(self, node) -> Optional[dict]:
        """Extract import details from an AST node.

        Returns:
            dict with keys:
            - 'module_name': str - the module being imported from
            - 'imported_names': list[str] - list of imported symbol names
            Returns None if extraction fails.
        """
        pass

    @abstractmethod
    def _convert_module_to_file_path(self, module_name: str) -> str:
        """Convert a module name to a file path using language-specific rules."""
        pass

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Resolve import relationships that can be resolved immediately.

        Resolves import relationships by finding the imported symbols.
        This logic is language-agnostic and reusable across languages.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseImportHandler.resolve_immediate called")

        # Query unresolved 'imports' relationships for this language only
        unresolved = reader.find_unresolved("imports", language=self.language)
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

        This is generic logic that works across languages.

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
        This can be overridden by subclasses if needed for language-specific complex resolution.
        """
        pass

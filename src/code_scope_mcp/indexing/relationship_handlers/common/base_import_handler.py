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

                    # Handle special case for "import all symbols" (e.g., PHP includes)
                    if imported_names == ['*']:
                        # Create a single unresolved relationship that will be expanded during resolution
                        writer.add_unresolved_relationship(
                            source_symbol_id=file_symbol_id,
                            source_qname=file_qname,
                            target_name='*',  # Special marker for "all symbols"
                            rel_type="imports",
                            needs_type="declares_class",
                            target_qname=None,
                            intermediate_symbol_qname=f"{target_file}:__FILE__",
                            target_resolver_name="BaseImportHandler"
                        )
                        self.logger.log(self.__class__.__name__, f"DEBUG: Created unresolved import for all symbols: {file_qname} -> * from {target_file}")
                    else:
                        # Create unresolved import relationships for each imported symbol
                        for imported_name in imported_names:
                            writer.add_unresolved_relationship(
                                source_symbol_id=file_symbol_id,
                                source_qname=file_qname,
                                target_name=imported_name,
                                rel_type="imports",
                                needs_type="declares_class",
                                target_qname=None,
                                intermediate_symbol_qname=f"{target_file}:__FILE__",
                                target_resolver_name="BaseImportHandler"
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
        Phase 2: Resolve import relationships in dynamic passes until no progress is made.

        This handles order-independent resolution by continuing to resolve imports
        until no progress is made in a complete cycle, properly handling forward references.

        Unlike the fixed 3-pass approach, this adapts to the complexity of dependency chains.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseImportHandler.resolve_immediate called")

        # Dynamic multi-pass resolution to handle arbitrary dependency chains
        max_passes = 10  # Reasonable upper limit to prevent infinite loops
        previous_unresolved_count = float('inf')
        current_pass = 0
        total_resolved = 0

        while current_pass < max_passes:
            current_pass += 1
            self.logger.log(self.__class__.__name__, f"DEBUG: Starting pass {current_pass} of import resolution")

            # Query unresolved 'imports' relationships for this language only
            unresolved = reader.find_unresolved("imports", language=self.language)
            unresolved_count = len(unresolved)
            self.logger.log(self.__class__.__name__, f"DEBUG: Found {unresolved_count} unresolved imports relationships")

            # If no progress made in this pass, we're likely stuck on circular dependencies
            if unresolved_count == previous_unresolved_count:
                self.logger.log(self.__class__.__name__, f"DEBUG: No progress in pass {current_pass}, exiting resolution loop")
                break
            previous_unresolved_count = unresolved_count

            # If no unresolved imports, we're done
            if unresolved_count == 0:
                self.logger.log(self.__class__.__name__, "DEBUG: All imports resolved")
                break

            resolved_count = 0
            for rel in unresolved:
                self.logger.log(self.__class__.__name__, f"DEBUG: Processing unresolved import: {rel['source_qname']} -> {rel['target_name']}")

                # Try to resolve the import relationship
                intermediate_qname = rel['intermediate_symbol_qname'] if 'intermediate_symbol_qname' in rel.keys() and rel['intermediate_symbol_qname'] else None
                target_result = self._resolve_import_target(rel['target_name'], intermediate_qname, reader)

                if target_result:
                    # Handle both single symbol (dict) and multiple symbols (list) cases
                    if isinstance(target_result, list):
                        # Multiple symbols case (e.g., PHP includes with '*')
                        for target_symbol in target_result:
                            self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved import: {rel['source_qname']} -> {target_symbol['qname']}")
                            writer.add_relationship(
                                source_symbol_id=rel['source_symbol_id'],
                                target_symbol_id=target_symbol['id'],
                                rel_type="imports",
                                source_qname=rel['source_qname'],
                                target_qname=target_symbol['qname']
                            )
                        resolved_count += 1  # Count as one resolved relationship (the '*')
                        total_resolved += len(target_result)  # But track actual relationships created
                    else:
                        # Single symbol case (dict)
                        self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved import: {rel['source_qname']} -> {target_result['qname']}")
                        writer.add_relationship(
                            source_symbol_id=rel['source_symbol_id'],
                            target_symbol_id=target_result['id'],
                            rel_type="imports",
                            source_qname=rel['source_qname'],
                            target_qname=target_result['qname']
                        )
                        resolved_count += 1
                        total_resolved += 1

                    # Delete the unresolved relationship (only after processing all targets for '*' case)
                    writer.delete_unresolved_relationship(rel['id'])
                    self.logger.log(self.__class__.__name__, "DEBUG: Import relationship resolved")
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve import target: {rel['target_name']}")

            self.logger.log(self.__class__.__name__, f"DEBUG: Pass {current_pass} resolved {resolved_count} imports")

        # Check remaining unresolved imports
        final_unresolved = reader.find_unresolved("imports", language=self.language)
        if final_unresolved:
            remaining_count = len(final_unresolved)
            self.logger.log(self.__class__.__name__, f"WARNING: {remaining_count} imports remain unresolved after {current_pass} passes")
            for rel in final_unresolved:
                self.logger.log(self.__class__.__name__, f"WARNING: Unresolved import: {rel['source_qname']} -> {rel['target_name']}")

            # Log performance summary
            self.logger.log(self.__class__.__name__, f"DEBUG: Import resolution summary: {total_resolved} resolved, {remaining_count} unresolved in {current_pass} passes")
        else:
            self.logger.log(self.__class__.__name__, f"DEBUG: All {total_resolved} imports resolved successfully in {current_pass} passes")

    def _resolve_import_target(self, target_name: str, intermediate_symbol_qname: str, reader: 'IndexReader'):
        """
        Resolve the target of an import relationship.

        This is generic logic that works across languages.

        Args:
            target_name: The name of the symbol being imported
            intermediate_symbol_qname: Optional hint about the source file
            reader: IndexReader instance

        Returns:
            Symbol dict if found, list of symbols if target_name='*', None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Resolving import target: {target_name}")

        # Handle special case for "import all symbols" (PHP includes)
        if target_name == '*':
            if intermediate_symbol_qname:
                # Get all symbols from the target file
                file_name = intermediate_symbol_qname.split(':')[0]
                target_file_qname_pattern = f"{file_name}:%"
                all_symbols_in_file = reader.find_symbols(qname=target_file_qname_pattern, match_type="like", language=self.language)

                # Filter out the file itself
                symbol_list = [symbol for symbol in all_symbols_in_file if not symbol['qname'].endswith(':__FILE__')]

                self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(symbol_list)} symbols to import from {file_name}")
                return symbol_list if symbol_list else None

            self.logger.log(self.__class__.__name__, f"DEBUG: Cannot resolve '*' import without intermediate_symbol_qname")
            return None

        # Standard resolution for named symbols
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

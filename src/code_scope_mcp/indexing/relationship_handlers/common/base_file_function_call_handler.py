from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler


class BaseFileFunctionCallHandler(BaseRelationshipHandler, ABC):
    """Abstract base class for file function call relationship handlers.

    This class contains the reusable logic for standalone function call resolution while
    delegating language-specific AST parsing and queries to subclasses.
    """

    relationship_type = "calls_file_function"
    phase_dependencies = ["imports"]

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved call relationships from AST for standalone function calls.

        PRIMARY PURPOSE: Analyze AST syntax to identify standalone function call candidates.
        READING FROM DATABASE: Allowed only as last resort for finding source symbol IDs.

        ⚠️  DATABASE READS SHOULD BE MINIMAL:
           - Only query for source symbol IDs by qname
           - Avoid complex lookups or relationship queries
           - Defer all resolution logic to Phase 2

        Creates unresolved relationships for standalone function calls.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseFileFunctionCallHandler.extract_from_ast called")

        # Get language-specific function call queries
        function_call_queries = self._get_function_call_queries()

        for query_text in function_call_queries:
            query = self.language_obj.query(query_text)
            captures = query.captures(tree.root_node)

            # Group captures by node for easier processing
            capture_groups = {}
            for node, capture_name in captures:
                if capture_name not in capture_groups:
                    capture_groups[capture_name] = []
                capture_groups[capture_name].append(node)

            # Process each standalone call
            call_nodes = capture_groups.get("call", [])
            function_nodes = capture_groups.get("function_name", [])

            for i, call_node in enumerate(call_nodes):
                function_name = None

                # Get the corresponding function name for this call
                if i < len(function_nodes):
                    function_name = function_nodes[i].text.decode('utf-8')

                self.logger.log(self.__class__.__name__, f"DEBUG: Processing standalone call {i} - function: {function_name}")

                if function_name:
                    # Extract call details using language-specific method
                    call_details = self._extract_function_from_node(call_node, function_name)
                    if not call_details:
                        continue

                    function_name = call_details['function_name']
                    source_qname = call_details['source_qname']

                    if source_qname:
                        # ⚠️  LAST RESORT: Find source symbol ID using reader
                        source_symbols = reader.find_symbols(qname=source_qname, language=self.language)
                        if source_symbols:
                            source_symbol_id = source_symbols[0]['id']
                            self.logger.log(self.__class__.__name__, f"DEBUG: Found source symbol id: {source_symbol_id}, creating unresolved relationship")
                            writer.add_unresolved_relationship(
                                source_symbol_id=source_symbol_id,
                                source_qname=source_qname,
                                target_name=function_name,
                                rel_type="calls_file_function",
                                needs_type="declares_file_function",
                                target_qname=None,
                                intermediate_symbol_qname=function_name  # Store just the function name for resolution
                            )
                        else:
                            self.logger.log(self.__class__.__name__, f"DEBUG: Source symbol not found: {source_qname}")

    @abstractmethod
    def _get_function_call_queries(self) -> list[str]:
        """Return language-specific tree-sitter queries for finding standalone function calls."""
        pass

    @abstractmethod
    def _extract_function_from_node(self, node, function_name: str) -> Optional[dict]:
        """Extract function call details from an AST node.

        Returns:
            dict with keys:
            - 'function_name': str - the name of the function being called
            - 'source_qname': str - the qualified name of the calling method/class.method
            Returns None if extraction fails.
        """
        pass

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Resolve standalone function calls using import relationships.

        Can resolve function calls that are imported from other files.
        This logic is language-agnostic and reusable across languages.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseFileFunctionCallHandler.resolve_immediate called")
        # Query unresolved 'calls_file_function' relationships for this language only
        unresolved = reader.find_unresolved("calls_file_function", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved calls_file_function relationships")

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Processing unresolved relationship: {rel['source_qname']} -> {rel['target_name']}")

            if rel['intermediate_symbol_qname']:
                # Try to resolve through imports
                target_symbol = self._find_function_through_imports(rel['intermediate_symbol_qname'], rel['source_qname'], reader)

                if target_symbol:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved relationship: {rel['source_qname']} -> {target_symbol['qname']}")
                    # Create resolved relationship
                    writer.add_relationship(
                        source_symbol_id=rel['source_symbol_id'],
                        target_symbol_id=target_symbol['id'],
                        rel_type="calls_file_function",
                        source_qname=rel['source_qname'],
                        target_qname=target_symbol['qname']
                    )
                    # Delete the unresolved relationship
                    writer.delete_unresolved_relationship(rel['id'])
                    self.logger.log(self.__class__.__name__, "DEBUG: Relationship resolved and unresolved deleted")
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: No target symbols found for {rel['intermediate_symbol_qname']}")
            else:
                self.logger.log(self.__class__.__name__, "DEBUG: No intermediate_symbol_qname found")

    def _find_function_through_imports(self, function_name: str, source_qname: str, reader: 'IndexReader'):
        """
        Find a function symbol by checking import relationships.

        This is generic logic that works across languages.

        Args:
            function_name: The function name being called (e.g., "helper_function")
            source_qname: The source method making the call (e.g., "Car.drive")
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """

        self.logger.log(self.__class__.__name__, f"DEBUG: _find_function_through_imports called with function_name='{function_name}', source_qname='{source_qname}'")

        # Extract the class name from source_qname (e.g., "Car.drive" -> "Car")
        source_parts = source_qname.split('.')
        if len(source_parts) != 2:
            self.logger.log(self.__class__.__name__, f"DEBUG: Invalid source_qname format: {source_qname}")
            return None

        class_name = source_parts[0]

        # Find the class symbol by searching for qnames that end with the class name
        class_symbols = reader.find_symbols(qname=f"%:{class_name}", match_type="like", language=self.language)
        if not class_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Class '{class_name}' not found")
            return None

        # Get the file that contains this class
        class_symbol = class_symbols[0]
        # Extract file_qname from the class qname (e.g., "file2.py:Car" -> "file2.py")
        file_qname = class_symbol['qname'].split(':')[0]

        # Look for resolved imports from this file that match the function name
        # We need to query the resolved relationships table since imports are resolved in Phase 2
        import_rels = reader.find_relationships(
            source_qname=f"{file_qname}:__FILE__",
            rel_type="imports",
            source_language=self.language,
            target_language=self.language
        )
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(import_rels)} resolved imports")
        for rel in import_rels:
            self.logger.log(self.__class__.__name__, f"DEBUG: Resolved import: {rel['source_qname']} -> {rel['target_qname']}")

        # Check each import to see if it matches our function name
        for import_rel in import_rels:
            target_qname = import_rel['target_qname']

            # Skip if target_qname is None
            if target_qname is None:
                continue

            # Check if this import ends with our function name
            if target_qname.endswith(f":{function_name}"):
                # Try to find the actual function symbol
                function_symbols = reader.find_symbols(qname=target_qname, language=self.language)
                if function_symbols:
                    return function_symbols[0]

        self.logger.log(self.__class__.__name__, f"DEBUG: Function '{function_name}' not found through imports")
        return None

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle complex function call resolution.

        This generic handler doesn't implement complex resolution.
        Language-specific subclasses can override this method if needed.
        """
        # Query remaining unresolved 'calls_file_function' relationships
        unresolved = reader.find_unresolved("calls_file_function", language=self.language)

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Complex resolution needed for: {rel['source_qname']} -> {rel['target_name']}")

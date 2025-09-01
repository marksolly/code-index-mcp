from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler


class BaseInstantiationHandler(BaseRelationshipHandler, ABC):
    """Abstract base class for instantiation relationship handlers.

    This class contains the reusable logic for instantiation resolution while
    delegating language-specific AST parsing and queries to subclasses.
    """

    relationship_type = "instantiates"

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved instantiation relationships from AST.

        PRIMARY PURPOSE: Analyze AST syntax to identify class instantiation candidates.
        READING FROM DATABASE: Allowed only as last resort for finding source symbol IDs.

        ⚠️  DATABASE READS SHOULD BE MINIMAL:
           - Only query for source symbol IDs by qname
           - Avoid complex lookups or relationship queries
           - Defer all resolution logic to Phase 2

        Creates unresolved relationships for class instantiations.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseInstantiationHandler.extract_from_ast called")

        # Get language-specific instantiation queries
        instantiation_queries = self._get_instantiation_queries()

        for query_text in instantiation_queries:
            query = self.language_obj.query(query_text)
            captures = query.captures(tree.root_node)

            for node, capture_name in captures:
                if capture_name == "instantiation":
                    # Extract instantiation details using language-specific method
                    instantiation_details = self._extract_instantiation_from_node(node)
                    if not instantiation_details:
                        continue

                    class_name = instantiation_details['class_name']
                    self.logger.log(self.__class__.__name__, f"DEBUG: Found instantiation: {class_name}")

                    # Find the containing context using language-specific method
                    source_qname = self._find_containing_context(node, file_qname)

                    if source_qname:
                        # ⚠️  LAST RESORT: Find source symbol ID using reader
                        source_symbols = reader.find_symbols(qname=source_qname, language=self.language)
                        if source_symbols:
                            source_symbol_id = source_symbols[0]['id']
                            self.logger.log(self.__class__.__name__, f"DEBUG: Found source symbol id: {source_symbol_id}, creating unresolved relationship")
                            # Create unresolved instantiation relationship
                            writer.add_unresolved_relationship(
                                source_symbol_id=source_symbol_id,
                                source_qname=source_qname,
                                target_name=class_name,
                                rel_type="instantiates",
                                needs_type="declares_class",
                                target_qname=None,  # Will be resolved
                            )
                        else:
                            self.logger.log(self.__class__.__name__, f"DEBUG: Source symbol not found: {source_qname}")

    @abstractmethod
    def _get_instantiation_queries(self) -> list[str]:
        """Return language-specific tree-sitter queries for finding instantiations."""
        pass

    @abstractmethod
    def _extract_instantiation_from_node(self, node) -> Optional[dict]:
        """Extract instantiation details from an AST node.

        Returns:
            dict with keys:
            - 'class_name': str - the name of the class being instantiated
            Returns None if extraction fails.
        """
        pass

    @abstractmethod
    def _find_containing_context(self, node, file_qname: str) -> Optional[str]:
        """Find the containing context (function/method) for an instantiation.

        Returns the qname of the containing function/method, or the file qname if at module level.
        Returns None if context cannot be determined.
        """
        pass

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Resolve instantiation relationships with current knowledge.

        Can resolve instantiations by:
        - Finding class symbols in the same file
        - Resolving through import relationships
        - Finding classes in imported modules

        This logic is language-agnostic and reusable across languages.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseInstantiationHandler.resolve_immediate called")

        # Query unresolved 'instantiates' relationships for this language only
        unresolved = reader.find_unresolved("instantiates", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved instantiates relationships")

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Processing unresolved instantiation: {rel['source_qname']} -> {rel['target_name']}")

            # Try to resolve the instantiation
            target_symbol = self._resolve_instantiation_target(rel, reader)

            if target_symbol:
                self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved instantiation: {rel['source_qname']} -> {target_symbol['qname']}")

                # Find the source symbol
                source_symbols = reader.find_symbols(qname=rel['source_qname'], language=self.language)
                if source_symbols:
                    source_symbol = source_symbols[0]

                    # Create resolved relationship
                    writer.add_relationship(
                        source_symbol_id=source_symbol['id'],
                        target_symbol_id=target_symbol['id'],
                        rel_type="instantiates",
                        source_qname=rel['source_qname'],
                        target_qname=target_symbol['qname']
                    )
                    # Delete the unresolved relationship
                    writer.delete_unresolved_relationship(rel['id'])
                    self.logger.log(self.__class__.__name__, "DEBUG: Instantiation relationship resolved")
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Could not find source symbol: {rel['source_qname']}")
            else:
                self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve instantiation target: {rel['target_name']}")

    def _resolve_instantiation_target(self, rel, reader: 'IndexReader'):
        """
        Resolve the target of an instantiation relationship.

        This is generic logic that works across languages.

        Args:
            rel: Unresolved relationship dict
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        target_name = rel['target_name']

        self.logger.log(self.__class__.__name__, f"DEBUG: Resolving instantiation target: {target_name}")

        # First, try to find the class by exact name match (same file)
        target_symbols = reader.find_symbols(name=target_name, language=self.language)
        # Filter for class symbols only
        class_symbols = [s for s in target_symbols if s['symbol_type'] == 'class']
        if class_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found class by name: {class_symbols[0]['qname']}")
            return class_symbols[0]

        # If not found by name, try to resolve through imports
        # First find symbols with the target name, then look for import relationships to those symbols
        potential_target_symbols = reader.find_symbols(name=target_name, language=self.language)
        for symbol in potential_target_symbols:
            # Look for import relationships that import this symbol
            import_rels = reader.find_relationships(rel_type="imports", target_id=symbol['id'], source_language=self.language, target_language=self.language)
            if import_rels:
                # Found an import relationship for this symbol
                self.logger.log(self.__class__.__name__, f"DEBUG: Found class through import: {symbol['qname']}")
                return symbol

        self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve instantiation target: {target_name}")
        return None

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle complex instantiation resolution.

        Can resolve:
        - Instantiations through factory patterns
        - Dynamic class resolution
        - Instantiations through complex expressions
        - Instantiations in conditional contexts

        This logic is language-agnostic and reusable across languages.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseInstantiationHandler.resolve_complex called")

        # Query remaining unresolved 'instantiates' relationships for this language only
        unresolved = reader.find_unresolved("instantiates", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved instantiates for complex resolution")

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Processing complex instantiation: {rel['source_qname']} -> {rel['target_name']}")

            # Try advanced resolution strategies
            target_symbol = self._resolve_complex_instantiation(rel, reader, writer)

            if target_symbol:
                self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved complex instantiation: {rel['source_qname']} -> {target_symbol['qname']}")

                # Find the source symbol
                source_symbols = reader.find_symbols(qname=rel['source_qname'], language=self.language)
                if source_symbols:
                    source_symbol = source_symbols[0]

                    # Create resolved relationship
                    writer.add_relationship(
                        source_symbol_id=source_symbol['id'],
                        target_symbol_id=target_symbol['id'],
                        rel_type="instantiates",
                        source_qname=rel['source_qname'],
                        target_qname=target_symbol['qname']
                    )
                    # Delete the unresolved relationship
                    writer.delete_unresolved_relationship(rel['id'])
                    self.logger.log(self.__class__.__name__, "DEBUG: Complex instantiation relationship resolved")
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Could not find source symbol for complex instantiation: {rel['source_qname']}")
            else:
                self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve complex instantiation: {rel['target_name']}")

    def _resolve_complex_instantiation(self, rel, reader: 'IndexReader', writer: 'IndexWriter'):
        """
        Resolve complex instantiation relationships using probabilistic approach.
        Embraces ambiguity by creating low-confidence relationships when certainty is impossible.

        This is generic logic that works across languages.

        Args:
            rel: Unresolved relationship dict
            reader: IndexReader instance
            writer: IndexWriter instance

        Returns:
            Symbol dict if found, None otherwise
        """
        target_name = rel['target_name']

        # Find ALL classes with this exact name (embracing ambiguity)
        all_matching_symbols = reader.find_symbols(name=target_name, language=self.language)
        class_symbols = [s for s in all_matching_symbols if s['symbol_type'] == 'class']

        if not class_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: No classes found with name: {target_name}")
            return None

        # Calculate confidence for each possible target and create relationships
        relationships_created = []
        source_file = rel['source_qname'].split(':')[0]

        for class_symbol in class_symbols:
            confidence = self._calculate_instantiation_confidence(rel, class_symbol, reader, source_file)

            # Only create relationships above minimum confidence threshold
            if confidence >= 0.1:
                self.logger.log(self.__class__.__name__,
                    f"DEBUG: Creating low-confidence instantiation: {rel['source_qname']} -> {class_symbol['qname']} (confidence: {confidence})")

                # Create resolved relationship with confidence score
                writer.add_relationship(
                    source_symbol_id=rel['source_symbol_id'],
                    target_symbol_id=class_symbol['id'],
                    rel_type="instantiates",
                    source_qname=rel['source_qname'],
                    target_qname=class_symbol['qname'],
                    confidence=confidence
                )
                relationships_created.append(class_symbol)

        if relationships_created:
            self.logger.log(self.__class__.__name__,
                f"DEBUG: Created {len(relationships_created)} low-confidence instantiation relationships for {target_name}")
            # Delete the unresolved relationship since we created resolved relationships
            writer.delete_unresolved_relationship(rel['id'])
            return relationships_created[0]  # Return first one for compatibility
        else:
            self.logger.log(self.__class__.__name__,
                f"DEBUG: No viable instantiation targets found for {target_name} (all below confidence threshold)")
            return None

    def _calculate_instantiation_confidence(self, rel, class_symbol, reader: 'IndexReader', source_file: str):
        """
        Calculate confidence score for a potential instantiation target.

        This is generic logic that works across languages.

        Args:
            rel: Unresolved relationship dict
            class_symbol: Potential target class symbol
            reader: IndexReader instance
            source_file: Source file path

        Returns:
            Float between 0.0 and 1.0
        """
        confidence = 0.0

        # High confidence if the class is imported into the source file
        import_rels = reader.find_relationships(
            rel_type="imports",
            target_id=class_symbol['id']
        )
        imported_files = {rel['source_qname'].split(':')[0] for rel in import_rels}

        if source_file in imported_files:
            confidence += 0.7  # High confidence for imported classes

        # Medium confidence for classes in the same package/module
        if self._are_in_same_package(source_file, class_symbol['file_path']):
            confidence += 0.3

        # Small base confidence for name match alone
        confidence += 0.1

        return min(confidence, 1.0)

    def _are_in_same_package(self, source_file: str, target_file: str):
        """
        Check if two files are in the same package/module.

        This is generic logic that can be overridden by subclasses for language-specific package detection.

        Args:
            source_file: Source file path
            target_file: Target file path

        Returns:
            True if files are in the same package
        """
        # Simple package detection based on directory structure
        source_parts = source_file.split('/')
        target_parts = target_file.split('/')

        # Compare directory paths (excluding filename)
        source_dir = '/'.join(source_parts[:-1]) if len(source_parts) > 1 else ''
        target_dir = '/'.join(target_parts[:-1]) if len(target_parts) > 1 else ''

        # Same directory = same package
        if source_dir == target_dir:
            return True

        # Check for common package patterns
        # Python: same parent directory (for package modules)
        if len(source_parts) > 1 and len(target_parts) > 1:
            if source_parts[-2] == target_parts[-2]:
                return True

        return False

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler


class BaseInheritsHandler(BaseRelationshipHandler, ABC):
    """Abstract base class for inheritance relationship handlers.

    This class provides the reusable logic for inheritance resolution that works
    across multiple programming languages. Most inheritance logic is language-agnostic,
    so subclasses typically only need to implement 1 abstract method.

    ## Inheritance Pattern

    To create a new language-specific inheritance handler:

    ```python
    class MyLanguageInheritsHandler(BaseInheritsHandler):
        def _get_inheritance_symbol_types(self) -> list[str]:
            # Return symbol types that can be inherited in your language
            return ['class', 'interface']  # For languages with interfaces
            # or return ['class']  # For Python-style single inheritance
    ```

    The base class handles all the complex resolution logic including:
    - Finding parent classes through imports
    - Resolving inheritance chains
    - Managing unresolved relationships
    - Coordinating with the database

    ## Why Minimal Abstract Methods?

    Inheritance resolution is mostly language-agnostic because:
    - Most languages resolve inheritance by finding symbols by name
    - Import resolution works the same way across languages
    - The core algorithm of "find parent class" is universal

    The only language-specific part is knowing which symbol types can be inherited.
    """

    relationship_type = "inherits"

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved inheritance relationships from AST.

        PRIMARY PURPOSE: Analyze AST syntax to identify inheritance candidates.
        READING FROM DATABASE: Not needed - inheritance handled by symbol extractor.

        ⚠️  DATABASE READS SHOULD BE MINIMAL:
           - Only query for source symbol IDs by qname
           - Avoid complex lookups or relationship queries
           - Defer all resolution logic to Phase 2

        This is typically handled by the symbol extractor, not here.
        Subclasses can override if language-specific AST extraction is needed.
        """
        pass

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Resolve inheritance relationships that can be resolved immediately.

        Resolves inheritance relationships by looking for imported symbols or
        symbols declared in the same file.
        This logic is language-agnostic and reusable across languages.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseInheritsHandler.resolve_immediate called")

        # Query unresolved 'inherits' relationships for this language only
        unresolved = reader.find_unresolved("inherits", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved inherits relationships")

        for rel in unresolved:
            self.logger.log(self.__class__.__name__, f"DEBUG: Processing unresolved inheritance: {rel['source_qname']} -> {rel['target_name']}")

            # Try to resolve the inheritance relationship
            target_symbol = self._resolve_inheritance_target(rel['target_name'], reader)

            if target_symbol:
                self.logger.log(self.__class__.__name__, f"DEBUG: Creating resolved inheritance: {rel['source_qname']} -> {target_symbol['qname']}")
                # Create resolved relationship
                writer.add_relationship(
                    source_symbol_id=rel['source_symbol_id'],
                    target_symbol_id=target_symbol['id'],
                    rel_type="inherits",
                    source_qname=rel['source_qname'],
                    target_qname=target_symbol['qname']
                )
                # Delete the unresolved relationship
                writer.delete_unresolved_relationship(rel['id'])
                self.logger.log(self.__class__.__name__, "DEBUG: Inheritance relationship resolved")
            else:
                self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve inheritance target: {rel['target_name']}")

    def _resolve_inheritance_target(self, target_name: str, reader: 'IndexReader'):
        """
        Resolve the target of an inheritance relationship.

        This is generic logic that works across languages.

        Args:
            target_name: The name of the class being inherited from
            reader: IndexReader instance

        Returns:
            Symbol dict if found, None otherwise
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Resolving inheritance target: {target_name}")

        # First, try to find the symbol by exact name match (for same-file inheritance)
        target_symbols = reader.find_symbols(name=target_name, language=self.language)
        # Filter for class symbols only
        class_symbols = [s for s in target_symbols if s['symbol_type'] == 'class']
        if class_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: Found target class by name: {class_symbols[0]['qname']}")
            return class_symbols[0]

        # If not found by name, try to find through imports
        # First find symbols with the target name, then look for import relationships to those symbols
        potential_target_symbols = reader.find_symbols(name=target_name, language=self.language)
        for symbol in potential_target_symbols:
            # Look for import relationships that import this symbol
            import_rels = reader.find_relationships(rel_type="imports", target_id=symbol['id'])
            if import_rels:
                # Found an import relationship for this symbol
                self.logger.log(self.__class__.__name__, f"DEBUG: Found target class through import: {symbol['qname']}")
                return symbol

        self.logger.log(self.__class__.__name__, f"DEBUG: Could not resolve inheritance target: {target_name}")
        return None

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle complex inheritance resolution.

        For now, this is a no-op as most inheritance should be resolved in Phase 2.
        Subclasses can override for language-specific complex resolution strategies.
        """
        pass

    @abstractmethod
    def _get_inheritance_symbol_types(self) -> list[str]:
        """Return the symbol types that represent inheritable constructs in this language.

        Returns:
            List of symbol types (e.g., ['class'] for Python, ['class', 'interface'] for others)
        """
        pass

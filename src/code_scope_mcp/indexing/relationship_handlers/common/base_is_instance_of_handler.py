from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

from ..base_relationship_handler import BaseRelationshipHandler
from ...models import Symbol


class BaseIsInstanceOfHandler(BaseRelationshipHandler, ABC):
    """Abstract base class for is_instance_of relationship handlers.

    This class contains the reusable logic for is_instance_of relationship resolution while
    delegating language-specific variable inference to subclasses.
    """

    relationship_type = "is_instance_of"

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved is_instance_of relationships from AST.

        Since is_instance_of relationships depend on instantiates relationships being resolved first,
        we don't need to extract anything in Phase 1. The resolution will happen in Phase 2
        by analyzing the resolved instantiates relationships.

        Subclasses can override this method if language-specific AST extraction is needed.
        """
        pass

    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 2: Create is_instance_of relationships based on resolved instantiates relationships.

        This logic is language-agnostic and reusable across languages.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: BaseIsInstanceOfHandler.resolve_immediate called")

        # Get all resolved instantiates relationships
        instantiates_rels = reader.find_relationships(
            rel_type="instantiates",
            source_language=self.language,
            target_language=self.language
        )
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(instantiates_rels)} instantiates relationships")

        for inst_rel in instantiates_rels:
            source_qname = inst_rel['source_qname']
            target_qname = inst_rel['target_qname']

            self.logger.log(self.__class__.__name__, f"DEBUG: Processing instantiates: {source_qname} -> {target_qname}")

            # Infer the variable name from the instantiation context using language-specific logic
            var_qname = self._infer_variable_qname(source_qname, target_qname)

            if var_qname:
                self.logger.log(self.__class__.__name__, f"DEBUG: Inferred variable qname: {var_qname}")

                # Find or create the variable symbol
                var_symbols = reader.find_symbols(qname=var_qname, language=self.language)
                if not var_symbols:
                    # Create the variable symbol if it doesn't exist
                    # We need to infer the file path and other details
                    source_symbols = reader.find_symbols(qname=source_qname, language=self.language)
                    if source_symbols:
                        source_symbol = source_symbols[0]
                        file_path = source_symbol['file_path']

                        # Create variable symbol
                        var_symbol = Symbol(
                            name=var_qname.split('.')[-1],
                            qname=var_qname,
                            symbol_type='variable',
                            file_path=file_path,
                            line_number=0,
                            language=self.language,
                            file_id=source_symbol['file_id']
                        )
                        added_symbol = writer.add_symbol(var_symbol)
                        var_symbol_id = added_symbol.id
                    else:
                        self.logger.log(self.__class__.__name__, f"DEBUG: Could not find source symbol for {source_qname}")
                        continue
                else:
                    var_symbol_id = var_symbols[0]['id']

                # Find the target class symbol
                target_symbols = reader.find_symbols(qname=target_qname, language=self.language)
                if target_symbols:
                    target_symbol = target_symbols[0]

                    # Create is_instance_of relationship
                    writer.add_relationship(
                        source_symbol_id=var_symbol_id,
                        target_symbol_id=target_symbol['id'],
                        rel_type="is_instance_of",
                        source_qname=var_qname,
                        target_qname=target_qname
                    )
                    self.logger.log(self.__class__.__name__, f"DEBUG: Created is_instance_of relationship: {var_qname} -> {target_qname}")
                else:
                    self.logger.log(self.__class__.__name__, f"DEBUG: Could not find target class symbol: {target_qname}")

    @abstractmethod
    def _infer_variable_qname(self, source_qname: str, target_qname: str) -> Optional[str]:
        """Infer the variable qname from the instantiation context.

        Args:
            source_qname: The qname of the method/function where instantiation occurred
            target_qname: The qname of the class being instantiated

        Returns:
            The inferred variable qname, or None if cannot be inferred
        """
        pass

    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """
        Phase 3: Handle complex is_instance_of resolution.

        For now, this is a no-op as most is_instance_of relationships should be resolved in Phase 2.
        Subclasses can override this method if needed for language-specific complex resolution.
        """
        pass

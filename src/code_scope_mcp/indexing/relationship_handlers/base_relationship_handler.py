from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Any

if TYPE_CHECKING:
    from ..writer import IndexWriter
    from ..reader import IndexReader
    from tree_sitter import Tree

class BaseRelationshipHandler(ABC):
    """Base class for unified relationship handlers that manage the complete lifecycle of a relationship type."""

    # Each handler declares its own capabilities
    relationship_type: str = None  # e.g., "calls", "instantiates"
    required_symbol_types: List[str] = []  # What symbol types this handler needs
    phase_dependencies: List[str] = []  # Other relationship types that must be resolved first

    def __init__(self, language: str, language_obj: Any, logger):
        self.language = language
        self.language_obj = language_obj
        self.logger = logger

    @abstractmethod
    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved relationships from AST.

        PRIMARY PURPOSE: Analyze AST syntax to identify relationship candidates.
        READING FROM DATABASE: Allowed only as last resort for finding source symbol IDs.

        ⚠️  DATABASE READS SHOULD BE MINIMAL:
           - Only query for source symbol IDs by qname
           - Avoid complex lookups or relationship queries
           - Defer all resolution logic to Phase 2

        Args:
            tree: Parsed AST tree for the file
            writer: IndexWriter for creating unresolved relationships
            reader: IndexReader for finding existing symbols (use sparingly!)
            file_qname: Qualified name of the file being processed
        """
        pass

    @abstractmethod
    def resolve_immediate(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """Phase 2: Resolve relationships with current knowledge."""
        pass

    @abstractmethod
    def resolve_complex(self, writer: 'IndexWriter', reader: 'IndexReader'):
        """Phase 3: Handle complex multi-step relationship resolution."""
        pass

    def _create_unresolved_relationship(self, writer, **kwargs):
        """Helper method to create unresolved relationships with proper target_resolver_name.

        Every relationship handler creates relationships that it itself is responsible for resolving.
        This ensures the database properly tracks which handler resolves each relationship.
        """
        if 'target_resolver_name' not in kwargs:
            kwargs['target_resolver_name'] = self.__class__.__name__

        writer.add_unresolved_relationship(**kwargs)

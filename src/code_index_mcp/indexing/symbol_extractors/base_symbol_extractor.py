from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..indexing_logger import IndexingLogger
from ..models import Symbol
from ..writer import IndexWriter


@dataclass
class SymbolExtractionContext:
    """Context object containing shared state for symbol extraction."""
    file_symbol: Symbol
    file_qname: str
    file_name: str  # Clean filename without the path, used for symbol qname construction
    writer: IndexWriter
    language_obj: Any
    tree: 'Tree'

class BaseSymbolExtractor(ABC):
    """Base class for all symbol extractors with common tree-sitter functionality."""

    def __init__(self, file_path: str, language: str, parser: Any, language_obj: Any, logger: IndexingLogger):
        self.logger = logger
        self.language = language
        self.file_path = file_path

        # Tree-sitter setup - passed in from orchestrator for efficiency
        self.parser = parser
        self.language_obj = language_obj

        # Extractor type for logging
        self._extractor_type = "generic"
        if f"/{self.language}/" in self.__module__:
            self._extractor_type = self.language

    def log(self, message, **dump_vars):
        """Standardized logging that includes the extractor class name."""
        self.logger.log(
            self.__class__.__name__,
            message,
            **dump_vars,
        )

    def _get_file_qname(self, file_path: str) -> str:
        """Convert file path to qualified name format with __FILE__ suffix."""
        return f"{Path(file_path).name}:__FILE__"

    @abstractmethod
    def extract_symbols(self, context: SymbolExtractionContext) -> List[Symbol]:
        """Extract symbols and immediate relationships using the provided context."""
        pass

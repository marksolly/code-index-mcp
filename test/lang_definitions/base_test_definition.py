from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseTestDefinition(ABC):
    """
    Abstract base class for language-specific test definitions.
    """

    @property
    @abstractmethod
    def language_name(self) -> str:
        """The name of the programming language."""
        pass

    @property
    @abstractmethod
    def supported_relationships(self) -> List[str]:
        """A list of relationship types supported by the language."""
        pass

    @abstractmethod
    def get_sample_files(self) -> List[str]:
        """Returns a list of paths to the sample code files for the language."""
        pass

    @abstractmethod
    def get_expected_relationships(self) -> List[Dict[str, Any]]:
        """
        Returns a list of dictionaries, each representing an expected relationship.
        Each dictionary should have the following keys:
        - 'source': The name of the source symbol.
        - 'target': The name of the target symbol.
        - 'type': The type of the relationship.
        - 'count': The expected number of times this relationship should appear.
        - 'source_qname': (Optional) The qualified name of the source symbol.
        - 'target_qname': (Optional) The qualified name of the target symbol.
        """
        pass

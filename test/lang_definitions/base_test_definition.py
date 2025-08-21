import os
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

    def get_files_to_index(self) -> List[tuple[str, str, str]]:
        """
        Reads sample files and returns them in the format expected by the orchestrator.
        """
        files = []
        for file_path in self.get_sample_files():
            with open(file_path, 'r') as f:
                files.append((os.path.abspath(file_path), self.language_name, f.read()))
        return files

    @abstractmethod
    def get_expected_relationships(self) -> List[Dict[str, Any]]:
        """
        Returns a list of dictionaries, each representing an expected relationship.
        Each dictionary should have the following keys, in this order:
        - 'source': The name of the source symbol.
        - 'source_qname': The qualified name of the source symbol.
        - 'type': The type of the relationship.
        - 'target': The name of the target symbol.
        - 'target_qname': The qualified name of the target symbol.
        - 'count': The expected number of times this relationship should appear.
        
        """
        pass

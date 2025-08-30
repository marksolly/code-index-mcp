from abc import ABC, abstractmethod
from typing import List

class LanguageDefinition(ABC):
    """
    Abstract base class for defining language-specific properties.
    """

    @property
    @abstractmethod
    def language_name(self) -> str:
        """The name of the programming language."""
        pass

    @property
    @abstractmethod
    def supported_symbol_types(self) -> List[str]:
        """A list of symbol types supported by the language."""
        pass

    @property
    @abstractmethod
    def supported_relationship_types(self) -> List[str]:
        """A list of relationship types supported by the language."""
        pass

    # REMOVED: uses_generic_handlers property is no longer needed
    # The orchestrator now discovers concrete handlers from language directories only

class PythonLanguageDefinition(LanguageDefinition):
    @property
    def language_name(self) -> str:
        return "python"

    @property
    def supported_symbol_types(self) -> List[str]:
        return [
            "file",
            "import",
            "class",
            "function",
            "method",
            "variable",
            "constant",
        ]

    @property
    def supported_relationship_types(self) -> List[str]:
        return [
            "imports",
            "calls_class_method",
            "calls_file_function",
            "instantiates",
            "is_instance_of",
            "inherits",
            "declares_file_function",
            "declares_class_method",
            "references_variable",
            "defines_namespace",
            "declares_class",
        ]




class JavascriptLanguageDefinition(LanguageDefinition):
    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def supported_symbol_types(self) -> List[str]:
        return [
            "file",
            "function",
            "class",
            "method",
            "constant",
            "variable",
            "import",
            "export",
        ]

    @property
    def supported_relationship_types(self) -> List[str]:
        return [
            "imports",
            "inherits",
            "instantiates",
            "is_instance_of",
            "declares_file_function",
            "declares_class_method",
            "declares_class",
            "declares_constant",
            "calls_file_function",
            "calls_class_method",
            "references_variable",
        ]

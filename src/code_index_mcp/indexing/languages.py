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

    @property
    @abstractmethod
    def uses_generic_handlers(self) -> List[str]:
        """
        A list of generic handler names that this language definition opts into.
        Generic handlers listed here will be used for this language.
        LanguageDefinition subclasses can override this method to change which
        generic handlers they use.

        Eg:
            return [
                "CallRelationshipHandler",
                "InstantiationRelationshipHandler",
                "InheritsRelationshipHandler",
            ]
        """
        pass

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

    @property
    def uses_generic_handlers(self) -> List[str]:
        return [
            "ImportRelationshipHandler",
            "InstantiationRelationshipHandler",
            "InheritsRelationshipHandler",
            "FileFunctionCallRelationshipHandler",
            "MemberFunctionCallRelationshipHandler",
            "IsInstanceOfRelationshipHandler",
        ]


class JavascriptLanguageDefinition(LanguageDefinition):
    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def supported_symbol_types(self) -> List[str]:
        return [
            "file",
            "import",
            "class",
            "function",
            "variable",
            "arrow_function",
        ]

    @property
    def supported_relationship_types(self) -> List[str]:
        return [
            "imports",
            "references_variable",
            "is_instance_of",
            "declares_class",
            "instantiates",
            "inherits",
            "declares_file_function",
            "declares_class_method",
            "calls",
        ]

    @property
    def uses_generic_handlers(self) -> List[str]:
        return [
            "CallRelationshipHandler",
        ]

from abc import ABC, abstractmethod

from tree_sitter_languages import get_language, get_parser

from ..indexing_logger import IndexingLogger
from ..writer import IndexWriter


class BaseSymbolExtractor(ABC):
    def __init__(self, file_path: str, language: str, logger: IndexingLogger):
        self.logger = logger
        self.language = language
        self.file_path = file_path
        self.parser = get_parser(language)
        self.language_obj = get_language(language)
        self._extractor_type = "generic"
        if f"/{self.language}/" in self.__module__:
            self._extractor_type = self.language

    @abstractmethod
    def extract_symbols(self, source_code: str, writer: IndexWriter):
        raise NotImplementedError

    def log(self, message, **dump_vars):
        self.logger.log(
            self.__class__.__name__,
            message,
            **dump_vars,
        )

    def _get_enclosing_class_qname(self, node, captures, file_qname: str) -> str | None:
        """
        Finds the qualified name of the enclosing class for a given AST node.

        This method traverses up the AST from the given node, looking for a
        'class_definition' node. If found, it constructs and returns the
        qualified name of that class.

        Args:
            node: The tree-sitter node to start the search from.
            captures: A list of all captures from the tree-sitter query.
            file_qname: The qualified name of the file being processed.

        Returns:
            The qualified name of the enclosing class, or None if the node
            is not inside a class.
        """
        current = node.parent
        while current is not None:
            if current.type == 'class_definition':
                name_node = current.child_by_field_name('name')
                if name_node:
                    class_name = name_node.text.decode()
                    enclosing_scope_qname = self._get_enclosing_scope_qname(current, captures, file_qname)
                    if enclosing_scope_qname == file_qname:
                        return f"{file_qname}:{class_name}"
                    else:
                        return f"{enclosing_scope_qname}.{class_name}"
            current = current.parent
        return None

    def _find_capture_in_node(self, captures, node, capture_name):
        """
        Finds the first captured node with a given name within a specific node.

        This utility is useful for identifying specific parts of a larger matched
        node from a tree-sitter query, such as finding the 'name' and 'value'
        captures within an 'assignment' node.

        Args:
            captures: A list of all captures from the tree-sitter query.
            node: The parent node to search within.
            capture_name: The name of the capture to find.

        Returns:
            The captured node if found, otherwise None.
        """
        for captured_node, name in captures:
            if name == capture_name:
                current = captured_node
                while current:
                    if current == node:
                        return captured_node
                    current = current.parent
        return None

    def _get_source_qname_for_node(self, node, file_qname: str, captures) -> str:
        """
        Determines the qualified name of the source symbol for a relationship.

        This method traverses up the AST from a given node to find the enclosing
        scope (e.g., a function or class) and returns its qualified name. This is
        used to correctly attribute relationships, like calls or instantiations,
        to the symbol that contains them.

        Args:
            node: The tree-sitter node from which to determine the source qname.
            file_qname: The qualified name of the file.
            captures: A list of all captures from the tree-sitter query.

        Returns:
            The qualified name of the enclosing scope, or the file's qname if
            the node is at the top level.
        """
        current = node.parent
        while current is not None:
            if current.type in ['function_definition', 'class_definition']:
                scope_name_node = current.child_by_field_name('name')
                if scope_name_node:
                    scope_name = scope_name_node.text.decode()
                    parent_scope_qname = self._get_enclosing_scope_qname(current, captures, file_qname)
                    if parent_scope_qname == file_qname:
                        return f"{parent_scope_qname}:{scope_name}"
                    else:
                        return f"{parent_scope_qname}.{scope_name}"
                break
            current = current.parent
        return file_qname

    def _get_enclosing_scope_qname(self, node, captures, file_qname: str) -> str:
        """
        Computes the qualified name of the enclosing scope for a given node.

        This method is used to determine the hierarchical context of a symbol
        definition. It traverses up the AST, collecting the names of enclosing
        classes to construct a nested qualified name (e.g., 'OuterClass.InnerClass').

        Args:
            node: The node for which to find the enclosing scope.
            captures: A list of all captures from the tree-sitter query.
            file_qname: The qualified name of the file.

        Returns:
            The qualified name of the enclosing scope, or the file's qname if
            the node is at the top level.
        """
        scope_parts = []
        current = node.parent
        while current is not None:
            if current.type in ['class_definition']:
                name_node = current.child_by_field_name('name')
                if name_node:
                    scope_parts.append(name_node.text.decode())
            current = current.parent

        if not scope_parts:
            return file_qname

        return ".".join(reversed(scope_parts))

    @abstractmethod
    def _handle_instantiation(self, node, captures, file_qname: str, writer: IndexWriter):
        """
        Handles the extraction of instantiation relationships.

        This method should be implemented by language-specific extractors to
        identify when a class is instantiated (e.g., `MyClass()`) and create
        the appropriate 'instantiates' relationships.

        Args:
            node: The tree-sitter node representing the instantiation.
            captures: A list of all captures from the tree-sitter query.
            file_qname: The qualified name of the file.
            writer: The IndexWriter to add symbols and relationships to.
        """
        pass

    @abstractmethod
    def _handle_call(self, node, captures, file_qname: str, writer: IndexWriter):
        """
        Handles the extraction of function/method call relationships.

        This method should be implemented by language-specific extractors to
        identify function or method calls and create the corresponding 'calls'
        relationships.

        Args:
            node: The tree-sitter node representing the call.
            captures: A list of all captures from the tree-sitter query.
            file_qname: The qualified name of the file.
            writer: The IndexWriter to add symbols and relationships to.
        """
        pass

    @abstractmethod
    def _handle_definition(self, node, captures, file_qname: str, writer: IndexWriter):
        """
        Handles the extraction of symbol definitions.

        This method should be implemented by language-specific extractors to
        process the definitions of symbols like classes, functions, and
        methods, creating the symbol entries in the index.

        Args:
            node: The tree-sitter node representing the definition.
            captures: A list of all captures from the tree-sitter query.
            file_qname: The qualified name of the file.
            writer: The IndexWriter to add symbols to.
        """
        pass

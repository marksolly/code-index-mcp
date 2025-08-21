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

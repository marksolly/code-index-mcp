import sqlite3
from abc import ABC, abstractmethod
from typing import List

from ..indexing_logger import IndexingLogger
from ..reader import IndexReader
from ..writer import IndexWriter


class BaseRelationshipAnalyzer(ABC):
    relationship_type = None

    def __init__(self, language: str, logger: IndexingLogger):
        self.logger = logger
        self.language = language
        self._analyzer_type = "generic"
        if f"/{self.language}/" in self.__module__:
            self._analyzer_type = self.language

    @abstractmethod
    def find_relationships(self, writer: IndexWriter, reader: IndexReader):
        raise NotImplementedError

    def _delete_resolved_relationships(self, writer: IndexWriter, resolved_ids: List[int]):
        if not resolved_ids:
            return
        writer.delete_unresolved_relationships(resolved_ids)
        self.log(f"Deleted {len(resolved_ids)} resolved relationships.")

    def log(self, message, **msg_context):
        self.logger.log(
            self.__class__.__name__,
            message,
            analyzer_type=self._analyzer_type,
            **msg_context,
        )

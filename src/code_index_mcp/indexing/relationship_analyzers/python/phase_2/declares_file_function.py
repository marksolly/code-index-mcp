from src.code_index_mcp.indexing.relationship_analyzers.base import BaseRelationshipAnalyzer
from src.code_index_mcp.indexing.indexing_logger import IndexingLogger
from src.code_index_mcp.indexing.reader import IndexReader
from src.code_index_mcp.indexing.writer import IndexWriter


class PythonDeclaresFileFunctionAnalyzer(BaseRelationshipAnalyzer):
    relationship_type = "declares_file_function"

    def __init__(self, language: str, logger: IndexingLogger):
        super().__init__(language, logger)

    def find_relationships(self, writer: IndexWriter, reader: IndexReader):
        self.log(f"Running {self.relationship_type} analyzer")
        unresolved_relations = reader.find_unresolved(self.relationship_type)

        # Convert rows to dicts for logging
        unresolved_list = [dict(row) for row in unresolved_relations]

        resolved_ids = []
        for unresolved in unresolved_relations:
            source_id = unresolved["source_symbol_id"]
            target_qname = unresolved["target_qname"]

            target_symbols = reader.find_symbols(qname=target_qname)
            if target_symbols:
                writer.add_relationship(
                    source_id,
                    target_symbols[0]["id"],
                    self.relationship_type,
                    unresolved["source_qname"],
                    target_qname,
                )
                resolved_ids.append(unresolved["id"])
                self.log(f"Resolved {self.relationship_type}", source_qname=unresolved["source_qname"], target_qname=target_qname)

        if resolved_ids:
            self._delete_resolved_relationships(writer, resolved_ids)

    def _delete_resolved_relationships(self, writer: IndexWriter, resolved_ids: list[int]):
        cursor = writer.db_connection.cursor()
        try:
            placeholders = ",".join("?" for _ in resolved_ids)
            cursor.execute(f"DELETE FROM unresolved_relationships WHERE id IN ({placeholders})", resolved_ids)
            writer.db_connection.commit()
            self.log(f"Resolved and deleted {len(resolved_ids)} '{self.relationship_type}' relationships.")
        finally:
            cursor.close()

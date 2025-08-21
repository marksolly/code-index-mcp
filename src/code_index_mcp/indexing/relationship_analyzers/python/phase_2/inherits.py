from src.code_index_mcp.indexing.relationship_analyzers.base import BaseRelationshipAnalyzer
from src.code_index_mcp.indexing.indexing_logger import IndexingLogger
from src.code_index_mcp.indexing.reader import IndexReader
from src.code_index_mcp.indexing.writer import IndexWriter


class PythonInheritsAnalyzer(BaseRelationshipAnalyzer):
    relationship_type = "inherits"

    def __init__(self, language: str, logger: IndexingLogger):
        super().__init__(language, logger)

    def find_relationships(self, writer: IndexWriter, reader: IndexReader):
        self.log(f"Running {self.relationship_type} analyzer")
        unresolved_relations = reader.find_unresolved(self.relationship_type)

        resolved_ids = []
        for unresolved in unresolved_relations:
            source_class_id = unresolved["source_symbol_id"]
            target_class_name = unresolved["target_name"]
            source_class_qname = unresolved["source_qname"]

            # Find the class symbol that is being inherited from
            target_classes = reader.find_symbols(name=target_class_name)
            # This is a simplification. A more robust solution would filter by symbol type and imports.
            if target_classes:
                writer.add_relationship(
                    source_class_id,
                    target_classes[0]["id"],
                    self.relationship_type,
                    source_class_qname,
                    target_classes[0]["qname"],
                )
                resolved_ids.append(unresolved["id"])
                self.log("Resolved inherits", class_qname=source_class_qname, parent_class_name=target_class_name)

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

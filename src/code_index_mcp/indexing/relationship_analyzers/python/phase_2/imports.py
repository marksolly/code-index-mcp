from ...base import BaseRelationshipAnalyzer
from ....reader import IndexReader
from ....writer import IndexWriter


class PythonImportAnalyzer(BaseRelationshipAnalyzer):
    """
    Resolves import relationships for Python.
    """

    relationship_type = "imports"

    def __init__(self, language: str, logger):
        super().__init__(language, logger)

    def find_relationships(self, writer: IndexWriter, reader: IndexReader):
        unresolved_imports = reader.find_unresolved(self.relationship_type)
        if not unresolved_imports:
            self.log("No unresolved imports found.")
            return

        resolved_ids = []
        for unresolved in unresolved_imports:
            source_id = unresolved["source_symbol_id"]
            target_name = unresolved["target_name"]
            source_qname = unresolved["source_qname"]

            # For now, assume the imported symbol is in another file in the project.
            # A more robust solution would handle built-ins and third-party libraries.
            target_symbols = reader.find_symbols(name=target_name)

            if target_symbols:
                for target_symbol in target_symbols:
                    writer.add_relationship(
                        source_id,
                        target_symbol["id"],
                        self.relationship_type,
                        source_qname,
                        target_symbol["qname"],
                    )
                    self.log(
                        "Resolved import",
                        source_qname=source_qname,
                        target_qname=target_symbol["qname"],
                    )
                resolved_ids.append(unresolved["id"])

        if resolved_ids:
            self._delete_resolved_relationships(writer, resolved_ids)

from src.code_index_mcp.indexing.relationship_analyzers.base import BaseRelationshipAnalyzer
from src.code_index_mcp.indexing.reader import IndexReader
from src.code_index_mcp.indexing.writer import IndexWriter


class GenericNameBasedResolverAnalyzer(BaseRelationshipAnalyzer):
    """
    A generic analyzer that resolves relationships by finding a target symbol
    based on its name.

    This analyzer is designed to be subclassed for specific relationship types
    (e.g., 'is_instance_of', 'inherits'). Subclasses should set the
    `relationship_type` class attribute.
    """

    def find_relationships(self, writer: IndexWriter, reader: IndexReader):
        """
        Finds and resolves relationships based on the target symbol's name.

        This method queries for unresolved relationships of the specified type,
        searches for a matching target symbol by name, and creates the
        relationship if a match is found.

        This is a simplification. A more robust solution would filter by
        symbol type and consider imports to resolve ambiguity.
        """
        self.log(f"Running {self.relationship_type} analyzer")
        unresolved_relations = reader.find_unresolved(self.relationship_type)

        resolved_ids = []
        for unresolved in unresolved_relations:
            source_symbol_id = unresolved["source_symbol_id"]
            target_name = unresolved["target_name"]
            source_qname = unresolved["source_qname"]

            # Find the symbol that is the target of the relationship
            target_symbols = reader.find_symbols(name=target_name)

            if target_symbols:
                # This is a simplification. A robust solution would handle multiple matches.
                target_symbol = target_symbols[0]
                writer.add_relationship(
                    source_symbol_id,
                    target_symbol["id"],
                    self.relationship_type,
                    source_qname,
                    target_symbol["qname"],
                )
                resolved_ids.append(unresolved["id"])
                self.log(
                    f"Resolved {self.relationship_type}",
                    source_qname=source_qname,
                    target_name=target_name,
                    target_qname=target_symbol["qname"],
                )

        if resolved_ids:
            self._delete_resolved_relationships(writer, resolved_ids)

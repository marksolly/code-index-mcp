from ....reader import IndexReader
from ....writer import IndexWriter
from ...base import BaseRelationshipAnalyzer


class GenericDeclarationAnalyzer(BaseRelationshipAnalyzer):
    """
    A generic analyzer that resolves relationships where the target's qualified
    name (qname) is already known and recorded in the unresolved_relationships
    table.

    This analyzer is particularly useful for resolving declaration relationships
    like 'declares_class_method' or 'declares_file_function', where the symbol
    extractor has already determined the precise qname of the declared symbol.

    It works by iterating through unresolved relationships that have a target_qname
    and resolving them if a corresponding symbol exists in the database.
    """

    relationship_type = "declares"

    def find_relationships(self, writer: IndexWriter, reader: IndexReader):
        """
        Finds and resolves relationships where the target_qname is already specified.
        """
        unresolved = reader.find_unresolved(target_qname__is_not_null=True)
        for row in unresolved:
            source_qname = row["source_qname"]
            target_qname = row["target_qname"]
            rel_type = row["rel_type"]

            target_symbols = reader.find_symbols(qname=target_qname)
            if not target_symbols:
                continue

            confidence = 1.0 / len(target_symbols)
            
            source_symbols = reader.find_symbols(qname=source_qname)
            if not source_symbols:
                continue

            for source_symbol in source_symbols:
                for target_symbol in target_symbols:
                    writer.add_relationship(
                        source_symbol_id=source_symbol["id"],
                        target_symbol_id=target_symbol["id"],
                        source_qname=source_qname,
                        target_qname=target_symbol["qname"],
                        rel_type=rel_type,
                        confidence=confidence,
                    )
            writer.delete_unresolved_relationship(row["id"])

from ...base import BaseRelationshipAnalyzer

class GenericInstantiationAnalyzer(BaseRelationshipAnalyzer):
    relationship_type = "instantiates"

    def find_relationships(self, writer, reader):
        self.writer = writer
        self.reader = reader

        unresolved_instantiations = self.reader.find_unresolved("instantiates")
        resolved_ids = []

        for unresolved in unresolved_instantiations:
            source_symbols = self.reader.find_symbols(qname=unresolved["source_qname"])
            if not source_symbols:
                continue
            source_symbol = source_symbols[0]

            target_name = unresolved["target_name"]

            # 1. Look for a class defined in the same file.
            target_symbols = self.reader.find_symbols(name=target_name)
            target_symbol = next((s for s in target_symbols if s["file_path"] == source_symbol["file_path"] and s["symbol_type"] == "class"), None)

            # 2. If not found, look for an imported symbol.
            if not target_symbol:
                file_qname = source_symbol["qname"].split(":")[0]
                file_symbols = self.reader.find_symbols(qname=file_qname)
                if file_symbols:
                    file_imports = self.reader.find_relationships(
                        rel_type="imports",
                        source_id=file_symbols[0]["id"]
                    )
                    for imp in file_imports:
                        imported_symbol_list = self.reader.find_symbols(id=imp["target_symbol_id"])
                        if not imported_symbol_list:
                            continue
                        
                        imported_symbol = imported_symbol_list[0]
                        if imported_symbol["name"] == target_name:
                            target_symbol = imported_symbol
                            break
            
            # 3. Fallback to original simplistic search
            if not target_symbol and target_symbols:
                # Create a low-confidence match for every possible symbol
                confidence = 1.0 / len(target_symbols) if target_symbols else 0.0
                for ts in target_symbols:
                    self.writer.add_relationship(
                        source_symbol_id=source_symbol["id"],
                        target_symbol_id=ts["id"],
                        rel_type="instantiates",
                        source_qname=source_symbol["qname"],
                        target_qname=ts["qname"],
                        confidence=confidence,
                    )
                resolved_ids.append(unresolved["id"])

            elif target_symbol:
                self.writer.add_relationship(
                    source_symbol_id=source_symbol["id"],
                    target_symbol_id=target_symbol["id"],
                    rel_type="instantiates",
                    source_qname=source_symbol["qname"],
                    target_qname=target_symbol["qname"],
                    confidence=1.0, # High confidence for direct matches
                )
                resolved_ids.append(unresolved["id"])

        if resolved_ids:
            self.writer.delete_unresolved_relationships(resolved_ids)

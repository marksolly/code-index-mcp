from src.code_index_mcp.indexing.relationship_analyzers.base import BaseRelationshipAnalyzer
from src.code_index_mcp.indexing.indexing_logger import IndexingLogger
from src.code_index_mcp.indexing.reader import IndexReader
from src.code_index_mcp.indexing.writer import IndexWriter


class PythonCallAnalyzer(BaseRelationshipAnalyzer):
    relationship_type = "calls"

    def __init__(self, language: str, logger: IndexingLogger):
        super().__init__(language, logger)

    def find_relationships(self, writer: IndexWriter, reader: IndexReader):
        self.log(f"Running {self.relationship_type} analyzer")
        unresolved_calls = reader.find_unresolved(self.relationship_type)

        resolved_ids = []
        for unresolved in unresolved_calls:
            source_id = unresolved["source_symbol_id"]
            target_name = unresolved["target_name"]
            source_qname = unresolved["source_qname"]
            needs_type = unresolved["needs_type_name"]

            if needs_type == "is_instance_of":
                intermediate_symbol_qname = unresolved["intermediate_symbol_qname"] if "intermediate_symbol_qname" in unresolved.keys() else None
                if not intermediate_symbol_qname:
                    continue

                if "super" in intermediate_symbol_qname:
                    # Special handling for super() calls
                    self.log("Attempting to resolve super() call", source_qname=source_qname, target_name=target_name)
                    # Find the class that contains the method making the super() call
                    declaring_class_rels = reader.find_relationships(target_qname=source_qname, rel_type="declares_class_method")
                    if declaring_class_rels:
                        class_id = declaring_class_rels[0]["source_symbol_id"]
                        # Find the parent class
                        inherits_rels = reader.find_relationships(source_id=class_id, rel_type="inherits")
                        if inherits_rels:
                            parent_class_id = inherits_rels[0]["target_symbol_id"]
                            method_symbol = self._find_method_in_hierarchy(parent_class_id, target_name, reader)
                            if method_symbol:
                                writer.add_relationship(
                                    source_id,
                                    method_symbol["id"],
                                    self.relationship_type,
                                    source_qname,
                                    method_symbol["qname"],
                                )
                                resolved_ids.append(unresolved["id"])
                                self.log("Resolved call (super method)", source_qname=source_qname, target_qname=method_symbol["qname"])
                    continue

                # This is a method call on an object instance.
                # We need to find the type of the object, then find the method on that type.
                instance_of_rels = reader.find_relationships(source_qname=intermediate_symbol_qname, rel_type="is_instance_of")
                if not instance_of_rels:
                    # Fallback for simple cases where the intermediate symbol is the variable name
                    # This is not robust, but can handle my_var.method() where my_var is not self.my_var
                    if ":" in source_qname:
                        scope_name = source_qname.split(":")[-1]
                    else:
                        scope_name = source_qname.split(".")[-1]
                    variable_qname = f"{scope_name}.{intermediate_symbol_qname}"
                    instance_of_rels = reader.find_relationships(source_qname=variable_qname, rel_type="is_instance_of")

                if instance_of_rels:
                    class_id = instance_of_rels[0]["target_symbol_id"]
                    method_symbol = self._find_method_in_hierarchy(class_id, target_name, reader)
                    if method_symbol:
                        writer.add_relationship(
                            source_id,
                            method_symbol["id"],
                            self.relationship_type,
                            source_qname,
                            method_symbol["qname"],
                        )
                        resolved_ids.append(unresolved["id"])
                        self.log("Resolved call (instance method)", source_qname=source_qname, target_qname=method_symbol["qname"])

            elif needs_type == "declares_class_method":
                # This is a self.method() call. Find the class that declares this method.
                self.log("Attempting to resolve self call", source_qname=source_qname, target_name=target_name)
                declaring_class_rels = reader.find_relationships(target_id=source_id, rel_type="declares_class_method")
                if not declaring_class_rels:
                    self.log("Failed to find declaring class for method", method_qname=source_qname)
                if declaring_class_rels:
                    class_id = declaring_class_rels[0]["source_symbol_id"]
                    method_symbol = self._find_method_in_hierarchy(class_id, target_name, reader)
                    if method_symbol:
                        writer.add_relationship(
                            source_id,
                            method_symbol["id"],
                            self.relationship_type,
                            source_qname,
                            method_symbol["qname"],
                        )
                        resolved_ids.append(unresolved["id"])
                        self.log("Resolved call (self method)", source_qname=source_qname, target_qname=method_symbol["qname"])

            elif needs_type == "declares_file_function":
                # Simplified: does not handle imports yet
                target_symbols = reader.find_symbols(name=target_name)
                if target_symbols:
                    writer.add_relationship(
                        source_id,
                        target_symbols[0]["id"],
                        self.relationship_type,
                        source_qname,
                        target_symbols[0]["qname"],
                    )
                    resolved_ids.append(unresolved["id"])
                    self.log("Resolved call (function)", source_qname=source_qname, target_name=target_name)

        if resolved_ids:
            self._delete_resolved_relationships(writer, resolved_ids)

    def _find_method_in_hierarchy(self, class_id: int, method_name: str, reader: IndexReader):
        """
        Recursively searches for a method in a class and its parents.
        """
        # Check the current class for the method
        class_symbol = reader.get_symbol_by_id(class_id)
        if not class_symbol:
            return None

        method_qname = f"{class_symbol['name']}.{method_name}"
        method_symbols = reader.find_symbols(qname=method_qname)
        if method_symbols:
            return method_symbols[0]

        # If not found, check parent classes
        inherits_rels = reader.find_relationships(source_id=class_id, rel_type="inherits")
        for rel in inherits_rels:
            parent_class_id = rel["target_symbol_id"]
            method_symbol = self._find_method_in_hierarchy(parent_class_id, method_name, reader)
            if method_symbol:
                return method_symbol

        return None

    def _delete_resolved_relationships(self, writer: IndexWriter, resolved_ids: list[int]):
        cursor = writer.db_connection.cursor()
        try:
            placeholders = ",".join("?" for _ in resolved_ids)
            cursor.execute(f"DELETE FROM unresolved_relationships WHERE id IN ({placeholders})", resolved_ids)
            writer.db_connection.commit()
            self.log(f"Resolved and deleted {len(resolved_ids)} 'calls' relationships.")
        finally:
            cursor.close()

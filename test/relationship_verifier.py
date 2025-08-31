import sqlite3
from src.code_index_mcp.db.database import DatabaseService
class RelationshipVerifier:
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service

    def _get_symbol_id(self, name, language, qname=None):
        conn = self.db_service.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT cs.id FROM code_symbols cs JOIN files f ON cs.file_id = f.id WHERE f.language = ?"
        params = [language]

        if qname:
            query += " AND cs.qname = ?"
            params.append(qname)
        else:
            query += " AND cs.name = ?"
            params.append(name)

        cursor.execute(query, tuple(params))
        result = cursor.fetchone()
        if result is None:
            # Debugging: Print available symbols if not found
            print(f"\nDEBUG: Symbol '{name}' (qname: '{qname}') not found. Available symbols with that name:")
            cursor.execute("SELECT name, qname FROM code_symbols WHERE name = ?", (name,))
            all_symbols = cursor.fetchall()
            if not all_symbols:
                print("  -> No symbols with that name found in the database.")
            else:
                for row in all_symbols:
                    print(f"  -> Found: name='{row['name']}', qname='{row['qname']}'")
            raise AssertionError(f"Symbol '{name}' with qname='{qname}' not found for language '{language}'")
        return result[0]

    def assert_symbol_exists(self, name, language, qname=None):
        """Asserts that a symbol exists in the database."""
        self._get_symbol_id(name, language, qname)

    def _get_relationship_type_id(self, name):
        conn = self.db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM relationship_types WHERE name = ?", (name,))
        result = cursor.fetchone()
        if result is None:
            raise AssertionError(f"Relationship type not found: '{name}'")
        return result[0]

    def _get_relationships(self, source_symbol_id, relationship_type_id, language=None):
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        if language:
            cursor.execute("""
                SELECT cs1.name as source_name, cs1.qname as source_qname, cs2.name as target_name, cs2.qname as target_qname, rt.name as rel_type
                FROM relationships r
                JOIN code_symbols cs1 ON r.source_symbol_id = cs1.id
                JOIN code_symbols cs2 ON r.target_symbol_id = cs2.id
                JOIN files f1 ON cs1.file_id = f1.id
                JOIN files f2 ON cs2.file_id = f2.id
                JOIN relationship_types rt ON r.type_id = rt.id
                WHERE r.source_symbol_id = ? AND r.type_id = ?
                AND f1.language = ? AND f2.language = ?
            """, (source_symbol_id, relationship_type_id, language, language))
        else:
            cursor.execute("""
                SELECT cs1.name as source_name, cs1.qname as source_qname, cs2.name as target_name, cs2.qname as target_qname, rt.name as rel_type
                FROM relationships r
                JOIN code_symbols cs1 ON r.source_symbol_id = cs1.id
                JOIN code_symbols cs2 ON r.target_symbol_id = cs2.id
                JOIN relationship_types rt ON r.type_id = rt.id
                WHERE r.source_symbol_id = ? AND r.type_id = ?
            """, (source_symbol_id, relationship_type_id))
        return cursor.fetchall()

    def assert_relationship(self, source, target, relationship_type, language, expected_count=1, source_qname=None, target_qname=None):
        source_id = self._get_symbol_id(source, language, source_qname)
        target_id = self._get_symbol_id(target, language, target_qname)
        rel_type_id = self._get_relationship_type_id(relationship_type)

        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # Add language filtering to ensure we only count relationships between symbols of the same language
        cursor.execute("""
            SELECT COUNT(*) FROM relationships r
            JOIN code_symbols cs1 ON r.source_symbol_id = cs1.id
            JOIN code_symbols cs2 ON r.target_symbol_id = cs2.id
            JOIN files f1 ON cs1.file_id = f1.id
            JOIN files f2 ON cs2.file_id = f2.id
            WHERE r.source_symbol_id = ? AND r.target_symbol_id = ? AND r.type_id = ?
            AND f1.language = ? AND f2.language = ?
        """, (source_id, target_id, rel_type_id, language, language))

        actual_count = cursor.fetchone()[0]

        if actual_count != expected_count:
            error_message = (
                f"AssertionError: Relationship '{relationship_type}' from '{source}' to '{target}' failed.\n"
                f"Expected count: {expected_count}, Actual count: {actual_count}.\n"
                f"Language: {language}\n"
            )

            error_message += self._dump_symbol_relationships(source_id, "source", source, language)
            error_message += self._dump_symbol_relationships(target_id, "target", target, language)

            raise AssertionError(error_message)

    def _dump_symbol_relationships(self, symbol_id, role, name, language=None):
        """Dumps all relationships for a given symbol."""
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # Outgoing relationships
        if language:
            cursor.execute("""
                SELECT cs2.name as target_name, cs2.qname as target_qname, rt.name as rel_type
                FROM relationships r
                JOIN code_symbols cs2 ON r.target_symbol_id = cs2.id
                JOIN code_symbols cs1 ON r.source_symbol_id = cs1.id
                JOIN files f2 ON cs2.file_id = f2.id
                JOIN relationship_types rt ON r.type_id = rt.id
                WHERE r.source_symbol_id = ? AND f2.language = ?
            """, (symbol_id, language))
        else:
            cursor.execute("""
                SELECT cs2.name as target_name, cs2.qname as target_qname, rt.name as rel_type
                FROM relationships r
                JOIN code_symbols cs2 ON r.target_symbol_id = cs2.id
                JOIN relationship_types rt ON r.type_id = rt.id
                WHERE r.source_symbol_id = ?
            """, (symbol_id,))
        outgoing = cursor.fetchall()

        # Incoming relationships
        if language:
            cursor.execute("""
                SELECT cs1.name as source_name, cs1.qname as source_qname, rt.name as rel_type
                FROM relationships r
                JOIN code_symbols cs1 ON r.source_symbol_id = cs1.id
                JOIN code_symbols cs2 ON r.target_symbol_id = cs2.id
                JOIN files f1 ON cs1.file_id = f1.id
                JOIN relationship_types rt ON r.type_id = rt.id
                WHERE r.target_symbol_id = ? AND f1.language = ?
            """, (symbol_id, language))
        else:
            cursor.execute("""
                SELECT cs1.name as source_name, cs1.qname as source_qname, rt.name as rel_type
                FROM relationships r
                JOIN code_symbols cs1 ON r.source_symbol_id = cs1.id
                JOIN relationship_types rt ON r.type_id = rt.id
                WHERE r.target_symbol_id = ?
            """, (symbol_id,))
        incoming = cursor.fetchall()

        dump = f"\n--- Relationships found for {role} symbol '{name}' (id: {symbol_id}) ---\n"
        if outgoing:
            dump += "  Outgoing:\n"
            for row in outgoing:
                dump += f"    - [{row['rel_type']}]-> {row['target_name']} ({row['target_qname']})\n"
        else:
            dump += "  No outgoing relationships.\n"

        if incoming:
            dump += "  Incoming:\n"
            for row in incoming:
                dump += f"    - [{row['rel_type']}]<- {row['source_name']} ({row['source_qname']})\n"
        else:
            dump += "  No incoming relationships.\n"

        return dump

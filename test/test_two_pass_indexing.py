"""
Tests for the two-pass indexing system.

This file contains tests specifically designed to validate the two-pass
indexing approach, particularly its ability to correctly resolve ambiguous
relationships where a single name might refer to multiple symbols (e.g., a
function and a class with the same name).

Run with:
uv run python3 -m unittest test/test_two_pass_indexing.py
"""

import unittest
import os
import shutil
import tempfile
from src.code_index_mcp.services.database import DatabaseService
from src.code_index_mcp.indexing.builder import IndexBuilder

class TestTwoPassIndexing(unittest.TestCase):

    def setUp(self):
        self.test_project_path = tempfile.mkdtemp(prefix="code_index_test_")
        self.db_path = os.path.join(self.test_project_path, ".index.db")
        
        # Create a file with an ambiguous call
        with open(os.path.join(self.test_project_path, "main.py"), "w") as f:
            f.write("""
class Ambiguous:
    pass

def Ambiguous():
    pass

def fn_foo():
    Ambiguous()
""")

        # Create files for unambiguous call tests
        with open(os.path.join(self.test_project_path, "unambiguous_module.py"), "w") as f:
            f.write("""
def my_function():
    pass

class MyClass:
    pass
""")

        with open(os.path.join(self.test_project_path, "caller_of_unambiguous.py"), "w") as f:
            f.write("""
from unambiguous_module import my_function, MyClass

def fn_baz():
    my_function()
    instance = MyClass()
""")

        self.db_service = DatabaseService(self.db_path)
        self.db_service.connect()
        self.db_service.initialize_db()

    def tearDown(self):
        self.db_service.close()
        shutil.rmtree(self.test_project_path)

    def test_ambiguous_relationship_resolution(self):
        # Run the indexer
        builder = IndexBuilder(self.db_service)
        builder.build_index(self.test_project_path)

        # Query the database to check the results
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # Get the fn_foo function's symbol id
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'fn_foo'")
        fn_foo_id = cursor.fetchone()['id']

        # Check the relationships from the caller
        cursor.execute("SELECT * FROM relationships WHERE source_symbol_id = ?", (fn_foo_id,))
        relationships = cursor.fetchall()

        self.assertEqual(len(relationships), 2, f"Expected exactly 2 relationships for fn_foo, but found {len(relationships)}")

        # Check for 'calls' and 'instantiates' relationships
        rel_types = set()
        for rel in relationships:
            cursor.execute("SELECT name FROM relationship_types WHERE id = ?", (rel['type_id'],))
            rel_types.add(cursor.fetchone()['name'])
            self.assertAlmostEqual(rel['confidence'], 0.5)

        self.assertIn("calls", rel_types)
        self.assertIn("instantiates", rel_types)

    def test_unambiguous_relationship_identification(self):
        # Run the indexer
        builder = IndexBuilder(self.db_service)
        builder.build_index(self.test_project_path)

        # Query the database to check the results
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # Get the 'fn_baz' function's symbol id
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'fn_baz'")
        fn_baz_id = cursor.fetchone()['id']

        # Get the 'my_function' symbol id
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'my_function' AND file_id IN (SELECT id FROM files WHERE path LIKE '%unambiguous_module.py')")
        my_function_id = cursor.fetchone()['id']

        # Get the 'MyClass' symbol id
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'MyClass' AND file_id IN (SELECT id FROM files WHERE path LIKE '%unambiguous_module.py')")
        my_class_id = cursor.fetchone()['id']

        self.assertIsNotNone(fn_baz_id, "Caller 'fn_baz' not found.")
        self.assertIsNotNone(my_function_id, "Target function 'my_function' not found.")
        self.assertIsNotNone(my_class_id, "Target class 'MyClass' not found.")

        # Check the relationships from 'fn_baz'
        cursor.execute("SELECT * FROM relationships WHERE source_symbol_id = ?", (fn_baz_id,))
        relationships = cursor.fetchall()

        # We expect 2 relationships: one call to my_function, one instantiation of MyClass
        self.assertEqual(len(relationships), 2, "Should have exactly 2 relationships from fn_baz.")

        calls_relationship = None
        instantiates_relationship = None

        for rel in relationships:
            cursor.execute("SELECT name FROM relationship_types WHERE id = ?", (rel['type_id'],))
            rel_type_name = cursor.fetchone()['name']
            if rel_type_name == "calls" and rel['target_symbol_id'] == my_function_id:
                calls_relationship = rel
            elif rel_type_name == "instantiates" and rel['target_symbol_id'] == my_class_id:
                instantiates_relationship = rel
        
        self.assertIsNotNone(calls_relationship, "A 'calls' relationship to my_function was not found.")
        self.assertIsNotNone(instantiates_relationship, "An 'instantiates' relationship to MyClass was not found.")

        self.assertAlmostEqual(calls_relationship['confidence'], 1.0, places=5, msg="Confidence for 'calls' relationship should be 1.0")
        self.assertAlmostEqual(instantiates_relationship['confidence'], 1.0, places=5, msg="Confidence for 'instantiates' relationship should be 1.0")

"""
This test file is the primary **integration test** for the entire indexing pipeline.

Its purpose is to ensure that the end-to-end process of scanning, analyzing,
and storing symbol and relationship data works correctly for a standard,
unambiguous set of code samples. It verifies that no regressions have occurred
in the core indexing functionality.

Execute with: `uv run python -m unittest test/test_graph_extraction.py`
"""

import unittest
import os
from datetime import datetime
from unittest.mock import Mock
from src.code_index_mcp.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer
from src.code_index_mcp.db.database import DatabaseServicefrom src.code_index_mcp.services.search_service import SearchService
from src.code_index_mcp.project_settings import ProjectSettings
from src.code_index_mcp.indexing.builder import IndexBuilder
from src.code_index_mcp.indexing.models import FileInfo, FileAnalysisResult

class TestGraphExtraction(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.test_data_path = os.path.join(os.path.dirname(__file__), 'small-samples')
        self.db_path = ":memory:"
        self.db_service = DatabaseService(db_path=self.db_path)
        self.db_service.initialize_db()
        self.index_builder = IndexBuilder(self.db_service)
        
        # Create a mock context
        mock_lifespan_context = Mock()
        mock_lifespan_context.base_path = self.test_data_path
        
        mock_request_context = Mock()
        mock_request_context.lifespan_context = mock_lifespan_context
        
        mock_ctx = Mock()
        mock_ctx.request_context = mock_request_context

        # Create and configure ProjectSettings
        self.project_settings = ProjectSettings(base_path=self.test_data_path, skip_load=True)
        def get_db_path_mock():
            return self.db_path
        self.project_settings.get_db_path = get_db_path_mock
        
        # Set the settings on the mock context
        mock_lifespan_context.settings = self.project_settings
        
        self.search_service = SearchService(ctx=mock_ctx, db_service=self.db_service)

    def _build_index(self):
        self.index_builder.build_index(self.test_data_path)

    def tearDown(self):
        self.db_service.close()

    def test_javascript_extraction(self):
        js_analyzer = TreeSitterAnalyzer(language_name='javascript')
        js_file_path = os.path.join(self.test_data_path, 'javascript', 'file1.js')
        
        result = js_analyzer.analyze_file(js_file_path)

        self.assertIsNotNone(result, "Analysis result should not be None")
        self.assertEqual(len(result['classes']), 1, "Should find 1 class")
        self.assertEqual(len(result['functions']), 1, "Should find 1 top-level function")

        extracted_class = result['classes'][0]
        self.assertEqual(extracted_class.name, 'Vehicle', "Class name should be 'Vehicle'")
        self.assertEqual(len(extracted_class.methods), 2, "Should find 2 methods in Vehicle class")
        
        method_names = [m.name for m in extracted_class.methods]
        self.assertIn('constructor', method_names, "Should find 'constructor' method")
        self.assertIn('start', method_names, "Should find 'start' method")

        # Verify qname of a method
        start_method = next((m for m in extracted_class.methods if m.name == 'start'), None)
        self.assertIsNotNone(start_method, "Should find 'start' method object")
        self.assertEqual(start_method.qname, 'Vehicle.start', "qname of start method should be 'Vehicle.start'")

        extracted_function = result['functions'][0]
        self.assertEqual(extracted_function.name, 'helper_function', "Function name should be 'helper_function'")

    def test_python_extraction(self):
        py_analyzer = TreeSitterAnalyzer(language_name='python')
        py_file_path = os.path.join(self.test_data_path, 'python', 'file1.py')

        result = py_analyzer.analyze_file(py_file_path)
        
        self.assertIsNotNone(result, "Analysis result should not be None")
        self.assertEqual(len(result['classes']), 1, "Should find 1 class")
        self.assertEqual(len(result['functions']), 1, "Should find 1 top-level function")

        extracted_class = result['classes'][0]
        self.assertEqual(extracted_class.name, 'Vehicle', "Class name should be 'Vehicle'")
        self.assertEqual(len(extracted_class.methods), 2, "Should find 2 methods in Vehicle class")

        method_names = [m.name for m in extracted_class.methods]
        self.assertIn('__init__', method_names, "Should find '__init__' method")
        self.assertIn('start', method_names, "Should find 'start' method")

        # Verify qname of a method
        start_method = next((m for m in extracted_class.methods if m.name == 'start'), None)
        self.assertIsNotNone(start_method, "Should find 'start' method object")
        self.assertEqual(start_method.qname, 'Vehicle.start', "qname of start method should be 'Vehicle.start'")

        extracted_function = result['functions'][0]
        self.assertEqual(extracted_function.name, 'helper_function', "Function name should be 'helper_function'")

    def test_python_class_member_indexing(self):
        self._build_index()
        py_file_path = os.path.join(self.test_data_path, 'python', 'file1.py')
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # The relationship type should be in the DB from initialization, but let's ensure it is for the test
        cursor.execute("INSERT OR IGNORE INTO relationship_types (name) VALUES ('contains_method')")
        conn.commit()

        # Find Vehicle class
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'Vehicle'")
        result = cursor.fetchone()
        self.assertIsNotNone(result, "Vehicle class symbol not found")
        vehicle_class_id = result[0]

        # Find start method
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'start' AND qname = 'Vehicle.start'")
        result = cursor.fetchone()
        self.assertIsNotNone(result, "start method symbol not found")
        start_method_id = result[0]

        # Verify 'contains_method' relationship
        cursor.execute("""
            SELECT 1 FROM relationships 
            WHERE source_symbol_id = ? AND target_symbol_id = ? 
            AND type_id = (SELECT id FROM relationship_types WHERE name = 'contains_method')
        """, (vehicle_class_id, start_method_id))
        self.assertIsNotNone(cursor.fetchone(), "Should find 'contains_method' relationship for start()")

    def test_python_inheritance_indexing(self):
        self._build_index()
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # The relationship type should be in the DB from initialization
        cursor.execute("INSERT OR IGNORE INTO relationship_types (name) VALUES ('inherits')")
        conn.commit()

        # Find Car class symbol from file2.py
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'Car'")
        result = cursor.fetchone()
        self.assertIsNotNone(result, "Car class symbol not found")
        car_class_id = result[0]

        # Find Vehicle class symbol from file1.py
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'Vehicle'")
        result = cursor.fetchone()
        self.assertIsNotNone(result, "Vehicle class symbol not found")
        vehicle_class_id = result[0]

        # Verify 'inherits' relationship
        cursor.execute("""
            SELECT 1 FROM relationships 
            WHERE source_symbol_id = ? AND target_symbol_id = ? 
            AND type_id = (SELECT id FROM relationship_types WHERE name = 'inherits')
        """, (car_class_id, vehicle_class_id))
        self.assertIsNotNone(cursor.fetchone(), "Should find 'inherits' relationship between Car and Vehicle")

    def test_python_call_relationships(self):
        self._build_index()

        # Search for the 'drive' method in the Python file
        results_str = self.search_service.find_symbols(pattern='drive', symbol_type='function')
        
        # Isolate the relevant part of the output for the Python `drive` function
        py_drive_section = ""
        for section in results_str.split('[function] drive'):
            if 'in: python/file2.py' in section:
                py_drive_section = section
                break
        
        self.assertTrue(py_drive_section, "Could not find 'drive' function from python/file2.py in search results")

        # --- Test 'calls' relationship ---
        expected_calls = {'start_engine', 'helper_function', 'get_identifier'}
        
        calls_line = ""
        for line in py_drive_section.split('\n'):
            if '-> calls:' in line:
                calls_line = line
                break
        
        self.assertTrue(calls_line, "Could not find 'calls' line in output")

        # Extract actual calls from "-> calls: call1, call2, ..."
        actual_calls_str = calls_line.split("-> calls:")[1].strip()
        actual_calls = {call.strip() for call in actual_calls_str.split(',')}
        
        self.assertTrue(expected_calls.issubset(actual_calls), f"Expected to find all of {expected_calls} in {actual_calls}")

        # --- Test 'called_by' relationship ---
        expected_called_by = {'service_car'}

        called_by_line = ""
        for line in py_drive_section.split('\n'):
            if '<- called_by:' in line:
                called_by_line = line
                break
        
        self.assertTrue(called_by_line, "Could not find 'called_by' line in output")

        actual_called_by_str = called_by_line.split("<- called_by:")[1].strip()
        actual_called_by = {caller.strip() for caller in actual_called_by_str.split(',')}

        self.assertTrue(expected_called_by.issubset(actual_called_by), f"Expected to find all of {expected_called_by} in {actual_called_by}")

    def test_python_member_function_call_relationships(self):
        self._build_index()
        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # Find Car.drive symbol
        cursor.execute("SELECT id FROM code_symbols WHERE qname = 'Car.drive'")
        result = cursor.fetchone()
        self.assertIsNotNone(result, "Car.drive symbol not found")
        drive_method_id = result[0]

        # Find Car.get_identifier symbol
        cursor.execute("SELECT id FROM code_symbols WHERE qname = 'Car.get_identifier'")
        result = cursor.fetchone()
        self.assertIsNotNone(result, "Car.get_identifier symbol not found")
        car_get_identifier_id = result[0]

        # Find Engine.get_identifier symbol
        cursor.execute("SELECT id FROM code_symbols WHERE qname = 'Engine.get_identifier'")
        result = cursor.fetchone()
        self.assertIsNotNone(result, "Engine.get_identifier symbol not found")
        engine_get_identifier_id = result[0]

        # Verify 'calls' relationship from Car.drive to Car.get_identifier
        cursor.execute("""
            SELECT 1 FROM relationships
            WHERE source_symbol_id = ? AND target_symbol_id = ?
            AND type_id = (SELECT id FROM relationship_types WHERE name = 'calls')
        """, (drive_method_id, car_get_identifier_id))
        self.assertIsNotNone(cursor.fetchone(), "Should find 'calls' relationship from Car.drive to Car.get_identifier")

        # Verify there is NO 'calls' relationship from Car.drive to Engine.get_identifier
        cursor.execute("""
            SELECT 1 FROM relationships
            WHERE source_symbol_id = ? AND target_symbol_id = ?
            AND type_id = (SELECT id FROM relationship_types WHERE name = 'calls')
        """, (drive_method_id, engine_get_identifier_id))
        self.assertIsNone(cursor.fetchone(), "Should NOT find 'calls' relationship from Car.drive to Engine.get_identifier")


if __name__ == '__main__':
    unittest.main()

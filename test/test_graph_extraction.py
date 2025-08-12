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
from src.code_index_mcp.services.database import DatabaseService
from src.code_index_mcp.services.search_service import SearchService
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
        py_analyzer = TreeSitterAnalyzer(language_name='python')
        py_file_path = os.path.join(self.test_data_path, 'python', 'file1.py')

        file_info = FileInfo(id=1, path=py_file_path, extension=".py", language='python', size=0, modified_time=datetime.now())
        analysis_data = py_analyzer.analyze_file(py_file_path)
        analysis_result = FileAnalysisResult(file_info, **analysis_data)

        self.index_builder.graph_builder.build_graph([analysis_result])

        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # The relationship type should be in the DB from initialization, but let's ensure it is for the test
        cursor.execute("INSERT OR IGNORE INTO relationship_types (name) VALUES ('contains_method')")
        conn.commit()

        # Find Vehicle class
        qname_vehicle = f"{os.path.basename(py_file_path)}:Vehicle"
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'Vehicle' AND qname = ?", (qname_vehicle,))
        result = cursor.fetchone()
        self.assertIsNotNone(result, f"Vehicle class symbol not found with qname {qname_vehicle}")
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
        py_analyzer = TreeSitterAnalyzer(language_name='python')
        
        # Analyze file1.py (contains Vehicle)
        py_file1_path = os.path.join(self.test_data_path, 'python', 'file1.py')
        file1_info = FileInfo(id=1, path=py_file1_path, extension=".py", language='python', size=0, modified_time=datetime.now())
        analysis1_data = py_analyzer.analyze_file(py_file1_path)
        analysis1_result = FileAnalysisResult(file1_info, **analysis1_data)

        # Analyze file2.py (contains Car that inherits Vehicle)
        py_file2_path = os.path.join(self.test_data_path, 'python', 'file2.py')
        file2_info = FileInfo(id=2, path=py_file2_path, extension=".py", language='python', size=0, modified_time=datetime.now())
        analysis2_data = py_analyzer.analyze_file(py_file2_path)
        analysis2_result = FileAnalysisResult(file2_info, **analysis2_data)

        self.index_builder.graph_builder.build_graph([analysis1_result, analysis2_result])

        conn = self.db_service.get_connection()
        cursor = conn.cursor()

        # The relationship type should be in the DB from initialization
        cursor.execute("INSERT OR IGNORE INTO relationship_types (name) VALUES ('inherits')")
        conn.commit()

        # Find Car class symbol from file2.py
        qname_car = f"{os.path.basename(py_file2_path)}:Car"
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'Car' AND qname = ?", (qname_car,))
        result = cursor.fetchone()
        self.assertIsNotNone(result, f"Car class symbol not found with qname {qname_car}")
        car_class_id = result[0]

        # Find Vehicle class symbol from file1.py
        qname_vehicle = f"{os.path.basename(py_file1_path)}:Vehicle"
        cursor.execute("SELECT id FROM code_symbols WHERE name = 'Vehicle' AND qname = ?", (qname_vehicle,))
        result = cursor.fetchone()
        self.assertIsNotNone(result, f"Vehicle class symbol not found with qname {qname_vehicle}")
        vehicle_class_id = result[0]

        # Verify 'inherits' relationship
        cursor.execute("""
            SELECT 1 FROM relationships 
            WHERE source_symbol_id = ? AND target_symbol_id = ? 
            AND type_id = (SELECT id FROM relationship_types WHERE name = 'inherits')
        """, (car_class_id, vehicle_class_id))
        self.assertIsNotNone(cursor.fetchone(), "Should find 'inherits' relationship between Car and Vehicle")

    def test_python_call_relationships(self):
        py_analyzer = TreeSitterAnalyzer(language_name='python')
        
        # Analyze all 3 python files
        analysis_results = []
        for i in range(1, 4):
            file_path = os.path.join(self.test_data_path, 'python', f'file{i}.py')
            file_info = FileInfo(id=i, path=file_path, extension=".py", language='python', size=0, modified_time=datetime.now())
            analysis_data = py_analyzer.analyze_file(file_path)
            analysis_results.append(FileAnalysisResult(file_info, **analysis_data))

        self.index_builder.graph_builder.build_graph(analysis_results)

        # Search for the 'drive' method
        results_str = self.search_service.find_symbols(pattern='drive', symbol_type='function')
        
        self.assertIn("-> calls: start, start_engine, helper_function", results_str)
        self.assertIn("<- called_by: service_car", results_str)


if __name__ == '__main__':
    unittest.main()

"""
Execute with: `uv run python -m unittest test/test_graph_extraction.py`
"""

import unittest
import os
from src.code_index_mcp.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer

class TestGraphExtraction(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.test_data_path = os.path.join(os.path.dirname(__file__), 'small-samples')

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

if __name__ == '__main__':
    unittest.main()

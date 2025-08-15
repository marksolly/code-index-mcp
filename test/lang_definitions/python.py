import os
from typing import List, Dict, Any
from test.lang_definitions.base_test_definition import BaseTestDefinition

class PythonTestDefinition(BaseTestDefinition):
    @property
    def language_name(self) -> str:
        return "python"

    @property
    def supported_relationships(self) -> List[str]:
        return ['calls', 'imports', 'inherits', 'instantiates', 'contains_method', 'references_variable']

    def get_sample_files(self) -> List[str]:
        return [
            os.path.join(os.path.dirname(__file__), '..', 'small-samples', 'python', 'file1.py'),
            os.path.join(os.path.dirname(__file__), '..', 'small-samples', 'python', 'file2.py'),
            os.path.join(os.path.dirname(__file__), '..', 'small-samples', 'python', 'file3.py'),
        ]

    def get_expected_relationships(self) -> List[Dict[str, Any]]:
        py_path = os.path.join('test', 'small-samples', 'python')
        return [
            # file2.py
            {'source': 'Car', 'target': 'Vehicle', 'type': 'inherits', 'count': 1, 'source_qname': 'file2.py:Car'},
            {'source': '__init__', 'target': 'Engine', 'type': 'instantiates', 'count': 1, 'source_qname': 'Car.__init__'},
            {'source': 'drive', 'target': 'start', 'type': 'calls', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Vehicle.start'},
            {'source': 'drive', 'target': 'start_engine', 'type': 'calls', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Engine.start_engine'},
            {'source': 'drive', 'target': 'helper_function', 'type': 'calls', 'count': 1, 'source_qname': 'Car.drive'},
            {'source': 'drive', 'target': 'get_identifier', 'type': 'calls', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Car.get_identifier'},
            {'source': 'Car', 'target': '__init__', 'type': 'contains_method', 'count': 1, 'source_qname': 'file2.py:Car', 'target_qname': 'Car.__init__'},
            {'source': 'Car', 'target': 'drive', 'type': 'contains_method', 'count': 1, 'source_qname': 'file2.py:Car', 'target_qname': 'Car.drive'},
            {'source': 'Car', 'target': 'get_identifier', 'type': 'contains_method', 'count': 1, 'source_qname': 'file2.py:Car', 'target_qname': 'Car.get_identifier'},
            {'source': 'drive', 'target': 'MY_CONSTANT1', 'type': 'references_variable', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'file1.py:MY_CONSTANT1'},
            {'source': 'drive', 'target': 'MY_CONSTANT2', 'type': 'references_variable', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'file1.py:MY_CONSTANT2'},
            
            # file3.py
            {'source': 'service_car', 'target': 'Car', 'type': 'instantiates', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'file2.py:Car'},
            {'source': 'service_car', 'target': 'drive', 'type': 'calls', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'Car.drive'},
            {'source': 'main', 'target': 'Garage', 'type': 'instantiates', 'count': 1},
            {'source': 'main', 'target': 'service_car', 'type': 'calls', 'count': 1, 'target_qname': 'Garage.service_car'},
        ]

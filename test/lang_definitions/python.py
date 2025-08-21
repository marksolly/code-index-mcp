import os
from typing import List, Dict, Any

from .base_test_definition import BaseTestDefinition

class PythonTestDefinition(BaseTestDefinition):
    @property
    def language_name(self) -> str:
        return "python"

    @property
    def supported_relationships(self) -> List[str]:
        return [
            'imports',
            'calls',
            'instantiates',
            'is_instance_of',
            'inherits',
            'declares_file_function',
            'declares_class_method',
            # 'declares_class',
            # 'declares_constant',
            # 'references_variable',
        ]

    def get_sample_files(self) -> List[str]:
        return [
            "test/small-samples/python/file1.py",
            "test/small-samples/python/file2.py",
            "test/small-samples/python/file3.py",
        ]

    def get_expected_relationships(self) -> List[Dict[str, Any]]:
        return [
            # file2.py imports
            {'source': 'file2.py', 'type': 'imports', 'target': 'MY_CONSTANT1', 'source_qname': 'file2.py', 'target_qname': 'file1.py:MY_CONSTANT1'},
            {'source': 'file2.py', 'type': 'imports', 'target': 'MY_CONSTANT2', 'source_qname': 'file2.py', 'target_qname': 'file1.py:MY_CONSTANT2'},
            {'source': 'file2.py', 'type': 'imports', 'target': 'Vehicle', 'source_qname': 'file2.py', 'target_qname': 'file1.py:Vehicle'},
            {'source': 'file2.py', 'type': 'imports', 'target': 'helper_function', 'source_qname': 'file2.py', 'target_qname': 'file1.py:helper_function'},
            
            # file3.py imports
            {'source': 'file3.py', 'type': 'imports', 'target': 'Car', 'source_qname': 'file3.py', 'target_qname': 'file2.py:Car'},
            
            # file2.py
            {'source': 'Car',   'target':    'Vehicle',        'type': 'inherits',            'count': 1, 'source_qname': 'file2.py:Car'},
            {'source': '__init__', 'target': 'Engine',         'type': 'instantiates',        'count': 1, 'source_qname': 'Car.__init__'},
            {'source': 'drive', 'target':    'start',          'type': 'calls',               'count': 1, 'source_qname': 'Car.drive',    'target_qname': 'Vehicle.start'},
            {'source': 'drive', 'target':    'start_engine',   'type': 'calls',               'count': 1, 'source_qname': 'Car.drive',    'target_qname': 'Engine.start_engine'},
            {'source': 'drive', 'target':    'helper_function', 'type': 'calls',              'count': 1, 'source_qname': 'Car.drive'},
            {'source': 'drive', 'target':    'get_identifier', 'type': 'calls',               'count': 1, 'source_qname': 'Car.drive',    'target_qname': 'Car.get_identifier'},
            {'source': 'Car',   'target':    '__init__',       'type': 'declares_class_method',   'count': 1, 'source_qname': 'file2.py:Car', 'target_qname': 'Car.__init__'},
            {'source': 'Car',   'target':    'drive',          'type': 'declares_class_method',   'count': 1, 'source_qname': 'file2.py:Car', 'target_qname': 'Car.drive'},
            {'source': 'Car',   'target':    'get_identifier', 'type': 'declares_class_method',   'count': 1, 'source_qname': 'file2.py:Car', 'target_qname': 'Car.get_identifier'},
            {'source': 'drive', 'target':    'MY_CONSTANT1',   'type': 'references_variable', 'count': 1, 'source_qname': 'Car.drive',    'target_qname': 'file1.py:MY_CONSTANT1'},
            {'source': 'drive', 'target':    'MY_CONSTANT2',   'type': 'references_variable', 'count': 1, 'source_qname': 'Car.drive',    'target_qname': 'file1.py:MY_CONSTANT2'},
            
            # file1.py
            {'source': 'file1.py', 'target': 'helper_function', 'type': 'declares_file_function', 'count': 1, 'source_qname': 'file1.py', 'target_qname': 'file1.py:helper_function'},

            # file3.py
            {'source': 'service_car', 'target': 'Car',         'type': 'instantiates', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'file2.py:Car'},
            {'source': 'car', 'target': 'Car', 'type': 'is_instance_of', 'count': 1, 'source_qname': 'service_car.car', 'target_qname': 'file2.py:Car'},
            {'source': 'service_car', 'target': 'drive',       'type': 'calls', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'Car.drive'},
            {'source': 'main',        'target': 'Garage',      'type': 'instantiates', 'count': 1},
            {'source': 'main',        'target': 'service_car', 'type': 'calls', 'count': 1, 'target_qname': 'Garage.service_car'},
        ]

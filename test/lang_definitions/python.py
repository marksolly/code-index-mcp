import os
from typing import List, Dict, Any

from .base_test_definition import BaseTestDefinition

class PythonTestDefinition(BaseTestDefinition):
    @property
    def language_name(self) -> str:
        return "python"



    @property
    def relationship_dependencies(self) -> Dict[str, List[str]]:
        """
        Defines the dependency order for Python relationships.
        Based on the 3-phase indexing pipeline:
        - Phase 1: Symbol extraction (declares_* relationships)
        - Phase 2: Intermediate resolution (imports, inherits, instantiates, is_instance_of)
        - Phase 3: Final resolution (calls_*, references_*)
        """
        return {
            # Declaration relationships (Phase 1) - no dependencies
            'declares_file_function': [],
            'declares_class': [],
            'declares_class_method': [],
            'declares_constant': [],

            # Phase 2: Intermediate resolution - depends on symbol declarations
            'imports': [],  # Foundational - no dependencies
            'inherits': ['declares_class'],
            'instantiates': ['declares_class'],
            'is_instance_of': ['declares_class', 'instantiates'],

            # Phase 3: Final resolution - depends on Phase 2 relationships
            'calls_file_function': ['imports', 'declares_file_function'],
            'calls_class_method': ['imports', 'inherits', 'declares_class', 'declares_class_method'],
            'references_variable': ['imports']  # references_variable depends on imports to resolve variable locations
        }

    def get_sample_files(self) -> List[str]:
        return [
            "test/small-samples/python/file1.py",
            "test/small-samples/python/file2.py",
            "test/small-samples/python/file3.py",
        ]

    def _define_expected_relationships(self) -> List[Dict[str, Any]]:
        return [
            # file2.py imports
            {'type': 'imports', 'source_qname': 'file2.py:__FILE__', 'target_qname': 'file1.py:MY_CONSTANT1',    'count': 1},
            {'type': 'imports', 'source_qname': 'file2.py:__FILE__', 'target_qname': 'file1.py:MY_CONSTANT2',    'count': 1},
            {'type': 'imports', 'source_qname': 'file2.py:__FILE__', 'target_qname': 'file1.py:Vehicle',         'count': 1},
            {'type': 'imports', 'source_qname': 'file2.py:__FILE__', 'target_qname': 'file1.py:helper_function', 'count': 1},
            
            # file3.py imports
            {'type': 'imports', 'source_qname': 'file3.py:__FILE__', 'target_qname': 'file2.py:Car',             'count': 1},
            
            # file2.py
            {'type': 'inherits',              'source_qname': 'file2.py:Car', 'target_qname': 'file1.py:Vehicle', 'count': 1},
            {'type': 'instantiates',          'source_qname': 'Car.__init__', 'target_qname': 'file2.py:Engine', 'count': 1},
            {'type': 'calls_class_method',    'source_qname': 'Car.drive',    'target_qname': 'Vehicle.start', 'count': 1},
            {'type': 'calls_class_method',    'source_qname': 'Car.drive',    'target_qname': 'Engine.start_engine', 'count': 1},
            {'type': 'calls_file_function',   'source_qname': 'Car.drive',    'target_qname': 'file1.py:helper_function', 'count': 1},
            {'type': 'calls_class_method',    'source_qname': 'Car.drive',    'target_qname': 'Car.get_identifier', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.py:Car', 'target_qname': 'Car.__init__', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.py:Car', 'target_qname': 'Car.drive', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.py:Car', 'target_qname': 'Car.get_identifier', 'count': 1},
            {'type': 'references_variable',   'source_qname': 'Car.drive',    'target_qname': 'file1.py:MY_CONSTANT1', 'count': 1},
            {'type': 'references_variable',   'source_qname': 'Car.drive',    'target_qname': 'file1.py:MY_CONSTANT2', 'count': 1},
            
            # file1.py
            {'type': 'declares_file_function', 'count': 1, 'source_qname': 'file1.py:__FILE__', 'target_qname': 'file1.py:helper_function'},
            {'type': 'declares_class', 'count': 1, 'source_qname': 'file1.py:__FILE__', 'target_qname': 'file1.py:Vehicle'},

            # file2.py
            {'type': 'declares_class', 'count': 1, 'source_qname': 'file2.py:__FILE__', 'target_qname': 'file2.py:Engine'},
            {'type': 'declares_class', 'count': 1, 'source_qname': 'file2.py:__FILE__', 'target_qname': 'file2.py:Car'},

            # file3.py
            {'type': 'declares_class', 'count': 1, 'source_qname': 'file3.py:__FILE__', 'target_qname': 'file3.py:Garage'},
            {'type': 'instantiates', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'file2.py:Car'},
            {'type': 'is_instance_of', 'count': 1, 'source_qname': 'service_car.car', 'target_qname': 'file2.py:Car'},
            {'type': 'is_instance_of', 'count': 1, 'source_qname': 'Garage.loan_car', 'target_qname': 'file2.py:Car'},
            {'type': 'calls_class_method', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'Car.drive'},
            {'type': 'instantiates', 'count': 1, 'source_qname': 'file3.py:main', 'target_qname': 'file3.py:Garage'},
            {'type': 'calls_class_method', 'count': 1, 'source_qname': 'file3.py:main', 'target_qname': 'Garage.service_car'},
        ]

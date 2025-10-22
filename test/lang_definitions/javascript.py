import os
from typing import List, Dict, Any
from test.lang_definitions.base_test_definition import BaseTestDefinition

class JavascriptTestDefinition(BaseTestDefinition):
    @property
    def language_name(self) -> str:
        return "javascript"

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
            "test/small-samples/javascript/dir1/file1.js",
            "test/small-samples/javascript/dir2/file2.js",
            "test/small-samples/javascript/file3.js",
        ]

    def _define_expected_relationships(self) -> List[Dict[str, Any]]:
        return [
            # file1.js declares_file_function
            {'type': 'declares_file_function', 'count': 1, 'source_qname': 'file1.js:__FILE__', 'target_qname': 'file1.js:helper_function'},
            {'type': 'declares_file_function', 'count': 1, 'source_qname': 'file1.js:__FILE__', 'target_qname': 'file1.js:test_caller'},
            {'type': 'calls_file_function',   'source_qname': 'file1.js:test_caller',    'target_qname': 'file1.js:helper_function', 'count': 1},

            # file2.js imports - these will be created by relationship handlers
            {'type': 'imports', 'source_qname': 'file2.js:__FILE__', 'target_qname': 'file1.js:MY_CONSTANT', 'count': 1},
            {'type': 'imports', 'source_qname': 'file2.js:__FILE__', 'target_qname': 'file1.js:Vehicle', 'count': 1},
            {'type': 'imports', 'source_qname': 'file2.js:__FILE__', 'target_qname': 'file1.js:helper_function', 'count': 1},
            {'type': 'imports', 'source_qname': 'file2.js:__FILE__', 'target_qname': 'file1.js:vehiclePolisher', 'count': 1},
            {'type': 'imports', 'source_qname': 'file2.js:__FILE__', 'target_qname': 'file1.js:test_caller', 'count': 1},
            {'type': 'inherits', 'count': 1, 'source_qname': 'file2.js:Car', 'target_qname': 'file1.js:Vehicle'},
            {'type': 'instantiates', 'count': 1, 'source_qname': 'Car.constructor', 'target_qname': 'file2.js:Engine'},
            {'type': 'calls_class_method', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Vehicle.start'},
            {'type': 'calls_class_method', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Engine.start_engine'},
            {'type': 'calls_file_function', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'file1.js:helper_function'},
            {'type': 'calls_class_method', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Car.get_identifier'},
            {'type': 'declares_class_method', 'count': 1, 'source_qname': 'file2.js:Car', 'target_qname': 'Car.constructor'},
            {'type': 'declares_class_method', 'count': 1, 'source_qname': 'file2.js:Car', 'target_qname': 'Car.drive'},
            {'type': 'declares_class_method', 'count': 1, 'source_qname': 'file2.js:Car', 'target_qname': 'Car.get_identifier'},
            {'type': 'references_variable', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'file1.js:MY_CONSTANT'},
            {'type': 'references_variable', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'file2.js:MAX_VEHICLE_SPEED'},

            # file3.js
            {'type': 'imports', 'source_qname': 'file3.js:__FILE__', 'target_qname': 'file2.js:Car', 'count': 1},
            {'type': 'instantiates', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'file2.js:Car'},
            {'type': 'calls_class_method', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'Car.drive'},
            {'type': 'instantiates', 'count': 1, 'source_qname': 'file3.js:main', 'target_qname': 'file3.js:Garage'},
            {'type': 'calls_class_method', 'count': 1, 'source_qname': 'file3.js:main', 'target_qname': 'Garage.service_car'},
        ]

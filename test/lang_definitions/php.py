import os
from typing import List, Dict, Any

from .base_test_definition import BaseTestDefinition

class PhpTestDefinition(BaseTestDefinition):
    @property
    def language_name(self) -> str:
        return "php"

    @property
    def relationship_dependencies(self) -> Dict[str, List[str]]:
        """
        Defines the dependency order for PHP relationships.
        Based on the 3-phase indexing pipeline:
        - Phase 1: Symbol extraction (declares_* relationships)
        - Phase 2: Intermediate resolution (imports, inherits, instantiates, is_instance_of)
        - Phase 3: Final resolution (calls_*, references_*)
        """
        return {
            # Phase 1 - no dependencies
            'declares_file_function': [],
            'declares_class': [],
            'declares_class_method': [],
            'declares_constant': [],

            # Phase 2 - depends on declarations
            'imports': [],
            'inherits': ['declares_class'],
            'instantiates': ['declares_class'],
            'is_instance_of': ['declares_class', 'instantiates'],

            # Phase 3 - depends on Phase 2
            'calls_file_function': ['imports', 'declares_file_function'],
            'calls_class_method': ['imports', 'inherits', 'declares_class', 'declares_class_method'],
            'references_variable': ['imports']
        }

    def get_sample_files(self) -> List[str]:
        return [
            "test/small-samples/php/file1.php",
            "test/small-samples/php/file2.php",
            "test/small-samples/php/file3.php",
        ]

    def _define_expected_relationships(self) -> List[Dict[str, Any]]:
        return [
            # file1.php declarations
            {'type': 'declares_constant', 'source_qname': 'file1.php:__FILE__', 'target_qname': 'file1.php:MY_CONSTANT1', 'count': 1},
            {'type': 'declares_constant', 'source_qname': 'file1.php:__FILE__', 'target_qname': 'file1.php:MY_CONSTANT2', 'count': 1},
            {'type': 'declares_file_function', 'source_qname': 'file1.php:__FILE__', 'target_qname': 'file1.php:helper_function', 'count': 1},
            {'type': 'declares_file_function', 'source_qname': 'file1.php:__FILE__', 'target_qname': 'file1.php:vehiclePolisher', 'count': 1},
            {'type': 'declares_class', 'source_qname': 'file1.php:__FILE__', 'target_qname': 'file1.php:Vehicle', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file1.php:Vehicle', 'target_qname': 'Vehicle.__construct', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file1.php:Vehicle', 'target_qname': 'Vehicle.start', 'count': 1},

            # file2.php imports and declarations
            {'type': 'imports', 'source_qname': 'file2.php:__FILE__', 'target_qname': 'file1.php:Vehicle', 'count': 1},
            {'type': 'imports', 'source_qname': 'file2.php:__FILE__', 'target_qname': 'file1.php:helper_function', 'count': 1},
            {'type': 'imports', 'source_qname': 'file2.php:__FILE__', 'target_qname': 'file1.php:MY_CONSTANT1', 'count': 1},
            {'type': 'imports', 'source_qname': 'file2.php:__FILE__', 'target_qname': 'file1.php:MY_CONSTANT2', 'count': 1},
            {'type': 'declares_class', 'source_qname': 'file2.php:__FILE__', 'target_qname': 'file2.php:Engine', 'count': 1},
            {'type': 'declares_class', 'source_qname': 'file2.php:__FILE__', 'target_qname': 'file2.php:Car', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.php:Engine', 'target_qname': 'Engine.__construct', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.php:Engine', 'target_qname': 'Engine.get_identifier', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.php:Engine', 'target_qname': 'Engine.start_engine', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.php:Car', 'target_qname': 'Car.__construct', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.php:Car', 'target_qname': 'Car.get_identifier', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file2.php:Car', 'target_qname': 'Car.drive', 'count': 1},

            # file2.php inheritance and instantiation
            {'type': 'inherits', 'source_qname': 'file2.php:Car', 'target_qname': 'file1.php:Vehicle', 'count': 1},
            {'type': 'instantiates', 'source_qname': 'Car.__construct', 'target_qname': 'file2.php:Engine', 'count': 1},

            # file2.php method calls and references
            {'type': 'calls_class_method', 'source_qname': 'Car.drive', 'target_qname': 'Vehicle.start', 'count': 1},
            {'type': 'calls_class_method', 'source_qname': 'Car.drive', 'target_qname': 'Engine.start_engine', 'count': 1},
            {'type': 'calls_file_function', 'source_qname': 'Car.drive', 'target_qname': 'file1.php:helper_function', 'count': 1},
            {'type': 'calls_class_method', 'source_qname': 'Car.drive', 'target_qname': 'Car.get_identifier', 'count': 1},
            {'type': 'references_variable', 'source_qname': 'Car.drive', 'target_qname': 'file1.php:MY_CONSTANT1', 'count': 1},
            {'type': 'references_variable', 'source_qname': 'Car.drive', 'target_qname': 'file1.php:MY_CONSTANT2', 'count': 1},

            # file3.php imports and declarations
            {'type': 'imports', 'source_qname': 'file3.php:__FILE__', 'target_qname': 'file2.php:Car', 'count': 1},
            {'type': 'declares_class', 'source_qname': 'file3.php:__FILE__', 'target_qname': 'file3.php:Garage', 'count': 1},
            {'type': 'declares_file_function', 'source_qname': 'file3.php:__FILE__', 'target_qname': 'file3.php:main', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file3.php:Garage', 'target_qname': 'Garage.__construct', 'count': 1},
            {'type': 'declares_class_method', 'source_qname': 'file3.php:Garage', 'target_qname': 'Garage.service_car', 'count': 1},

            # file3.php instantiation and type relationships
            {'type': 'instantiates', 'source_qname': 'Garage.__construct', 'target_qname': 'file2.php:Car', 'count': 1},
            {'type': 'instantiates', 'source_qname': 'Garage.service_car', 'target_qname': 'file2.php:Car', 'count': 1},
            {'type': 'instantiates', 'source_qname': 'file3.php:main', 'target_qname': 'file3.php:Garage', 'count': 1},
            {'type': 'is_instance_of', 'source_qname': 'Garage.loan_car', 'target_qname': 'file2.php:Car', 'count': 1},
            {'type': 'is_instance_of', 'source_qname': 'Garage.service_car.car', 'target_qname': 'file2.php:Car', 'count': 1},

            # file3.php method calls
            {'type': 'calls_class_method', 'source_qname': 'Garage.service_car', 'target_qname': 'Car.drive', 'count': 1},
            {'type': 'calls_class_method', 'source_qname': 'file3.php:main', 'target_qname': 'Garage.service_car', 'count': 1},
        ]

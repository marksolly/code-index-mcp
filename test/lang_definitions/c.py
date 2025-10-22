import os
from typing import List, Dict, Any

from .base_test_definition import BaseTestDefinition

class CTestDefinition(BaseTestDefinition):
    @property
    def language_name(self) -> str:
        return "c"

    @property
    def relationship_dependencies(self) -> Dict[str, List[str]]:
        """
        Defines the dependency order for C relationships.
        Based on the 3-phase indexing pipeline:
        - Phase 1: Symbol extraction (declares_* relationships)
        - Phase 2: Intermediate resolution (imports - no dependencies)
        - Phase 3: Final resolution (calls_* and references_*)

        Note: Probabilistic relationships (e.g., from conditional includes) may leave
        some imports unresolved, which is expected behavior documented in the implementation plan.
        """
        return {
            # Declaration relationships (Phase 1) - no dependencies
            'declares_file_function': [],
            'declares_struct': [],
            'declares_typedef': [],
            'declares_enum': [],

            # Phase 2: Intermediate resolution
            'imports': [],  # Foundational - no dependencies (some may remain unresolved due to conditional compilation)

            # Phase 3: Final resolution - depends on Phase 2 relationships
            'calls_file_function': ['imports', 'declares_file_function'],
            'references_variable': ['imports'],
            'uses': ['imports', 'declares_struct', 'declares_typedef', 'declares_enum'],
            'type_of': ['imports', 'declares_struct', 'declares_typedef', 'declares_enum']
        }

    def get_sample_files(self) -> List[str]:
        """
        Include all C test files. The indexer will process them and discover
        the conditional includes during import resolution, demonstrating
        the probabilistic relationship scenarios.
        """
        return [
            "test/small-samples/c/main.c",
            "test/small-samples/c/shlib/utils.h",
            "test/small-samples/c/shlib/types.h",
            "test/small-samples/c/platform/windows_platform.h",
            "test/small-samples/c/platform/linux_platform.h",
            "test/small-samples/c/types_usage.c",
        ]

    def _define_expected_relationships(self) -> List[Dict[str, Any]]:
        """
        Define expected relationships based on our C test files.

        These relationships test the core functionality:
        - Basic function declarations and calls
        - Import relationships
        - Variable references
        - Preprocessor ambiguity (demonstrated by conditional includes)

        The probabilistic relationships from conditional includes would be
        tested in integration scenarios, not basic unit tests.
        """
        return [
            # Import relationships
            {'type': 'imports', 'source_qname': 'main.c:__FILE__', 'target_qname': 'utils.h:__FILE__', 'count': 1},

            # Function declarations in header file
            {'type': 'declares_file_function', 'source_qname': 'utils.h:__FILE__', 'target_qname': 'utils.h:print_hello', 'count': 1},
            {'type': 'declares_file_function', 'source_qname': 'utils.h:__FILE__', 'target_qname': 'utils.h:add_numbers', 'count': 1},
            {'type': 'declares_file_function', 'source_qname': 'utils.h:__FILE__', 'target_qname': 'utils.h:calculate_average', 'count': 1},
            {'type': 'declares_file_function', 'source_qname': 'utils.h:__FILE__', 'target_qname': 'utils.h:multiply_numbers', 'count': 1},

            # Function declarations in implementation file
            {'type': 'declares_file_function', 'source_qname': 'main.c:__FILE__', 'target_qname': 'main.c:main', 'count': 1},
            {'type': 'declares_file_function', 'source_qname': 'main.c:__FILE__', 'target_qname': 'main.c:process_data', 'count': 1},

            # Function calls from main.c to utils.h functions
            {'type': 'calls_file_function', 'source_qname': 'main.c:main', 'target_qname': 'utils.h:print_hello', 'count': 1},
            {'type': 'calls_file_function', 'source_qname': 'main.c:main', 'target_qname': 'utils.h:add_numbers', 'count': 1},
            {'type': 'calls_file_function', 'source_qname': 'main.c:main', 'target_qname': 'utils.h:calculate_average', 'count': 1},
            {'type': 'calls_file_function', 'source_qname': 'main.c:process_data', 'target_qname': 'utils.h:multiply_numbers', 'count': 1},

            # Variable references (global_counter usage in main.c)
            {'type': 'references_variable', 'source_qname': 'main.c:main', 'target_qname': 'main.c:global_counter', 'count': 1},

            # Type declarations in types.h
            {'type': 'declares_struct', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:Point', 'count': 1},
            {'type': 'declares_struct', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:Rectangle', 'count': 1},
            {'type': 'declares_struct', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:User', 'count': 1},

            {'type': 'declares_enum', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:Color', 'count': 1},
            {'type': 'declares_enum', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:Status', 'count': 1},

            {'type': 'declares_typedef', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:Point_t', 'count': 1},
            {'type': 'declares_typedef', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:User_t', 'count': 1},
            {'type': 'declares_typedef', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:Color_t', 'count': 1},
            {'type': 'declares_typedef', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:HttpStatus', 'count': 1},
            {'type': 'declares_typedef', 'source_qname': 'types.h:__FILE__', 'target_qname': 'types.h:Person', 'count': 1},

            # Import relationship for types_usage.c
            {'type': 'imports', 'source_qname': 'types_usage.c:__FILE__', 'target_qname': 'types.h:__FILE__', 'count': 1},

            # 'uses' relationships from types_usage.c
            {'type': 'uses', 'source_qname': 'types_usage.c:global_point', 'target_qname': 'types.h:Point_t', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:global_color', 'target_qname': 'types.h:Color_t', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:global_status', 'target_qname': 'types.h:HttpStatus', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:print_point', 'target_qname': 'types.h:Point_t', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:print_rectangle', 'target_qname': 'types.h:Rectangle', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:print_user', 'target_qname': 'types.h:User_t', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:print_color', 'target_qname': 'types.h:Color_t', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:print_status', 'target_qname': 'types.h:HttpStatus', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:process_person', 'target_qname': 'types.h:Person', 'count': 1},
            {'type': 'uses', 'source_qname': 'types_usage.c:main', 'target_qname': 'types.h:Point_t', 'count': 1}, # local variable p
            {'type': 'uses', 'source_qname': 'types_usage.c:main', 'target_qname': 'types.h:Rectangle', 'count': 1}, # local variable r
            {'type': 'uses', 'source_qname': 'types_usage.c:main', 'target_qname': 'types.h:User_t', 'count': 1}, # local variable user
            {'type': 'uses', 'source_qname': 'types_usage.c:main', 'target_qname': 'types.h:Person', 'count': 1}, # local variable person

            # 'type_of' relationships (only for typedefs that have symbols)
            {'type': 'type_of', 'source_qname': 'types.h:Point_t', 'target_qname': 'types.h:Point', 'count': 1}, # typedef Point_t -> struct Point
            {'type': 'type_of', 'source_qname': 'types.h:User_t', 'target_qname': 'types.h:User', 'count': 1}, # typedef User_t -> struct User
            {'type': 'type_of', 'source_qname': 'types.h:Color_t', 'target_qname': 'types.h:Color', 'count': 1}, # typedef Color_t -> enum Color
            {'type': 'type_of', 'source_qname': 'types.h:HttpStatus', 'target_qname': 'types.h:Status', 'count': 1}, # typedef HttpStatus -> enum Status
        ]

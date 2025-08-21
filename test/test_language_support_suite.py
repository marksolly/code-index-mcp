"""
Language Support Test Suite

This script runs a series of tests to verify language support for code indexing.
It dynamically discovers and loads test definitions for various programming languages.

Usage examples with `uv run`:

1. Run all language tests:
   uv run python test/test_language_support_suite.py --failfast

2. Run tests for a single language (e.g., Python):
   uv run python test/test_language_support_suite.py --language=python --failfast
"""
import unittest
import os
import importlib
import inspect
import sys
import argparse
import time
import re

# Add project root to the Python path to allow running from any directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.code_index_mcp.db.database import DatabaseService
from src.code_index_mcp.indexing.orchestrator import IndexingOrchestrator
from src.code_index_mcp.indexing.indexing_logger import IndexingLogger
from test.relationship_verifier import RelationshipVerifier
from test.lang_definitions.base_test_definition import BaseTestDefinition

class DebugOptions:
    def __init__(self):
        self.symbol_names = None
        self.language = None

class TestLanguageSupportSuite(unittest.TestCase):
    language_to_test = None
    db_service = None
    verifier = None
    debug_options = DebugOptions()
    auto_debug = True
    fail_fast = False

    @classmethod
    def setUpClass(cls):
        cls.rebuild_index()

    @classmethod
    def tearDownClass(cls):
        if cls.db_service:
            cls.db_service.close()

    @classmethod
    def rebuild_index(cls):
        if cls.db_service:
            cls.db_service.close()

        db_path = os.path.join(project_root, 'test_code_index.db')
        cls.db_service = DatabaseService(db_path)
        cls.db_service.delete_db()
        cls.db_service.initialize_db()

        logger = IndexingLogger(enabled=False)
        if cls.debug_options.symbol_names and cls.debug_options.language:
            logger = IndexingLogger(
                enabled=True,
                filters={
                    'language': [cls.debug_options.language],
                    'symbol_names': cls.debug_options.symbol_names
                }
            )

        orchestrator = IndexingOrchestrator(project_root, cls.db_service.get_connection(), logger)

        files_to_index = []
        language_to_test = cls.language_to_test
        definitions_path = os.path.join(os.path.dirname(__file__), 'lang_definitions')
        for filename in os.listdir(definitions_path):
            if filename.endswith('.py') and not filename.startswith('__') and not filename.startswith('base_'):
                module_name = f"test.lang_definitions.{filename[:-3]}"
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseTestDefinition) and obj is not BaseTestDefinition:
                        definition = obj()
                        if language_to_test and definition.language_name != language_to_test:
                            continue
                        for file_path, lang, code in definition.get_files_to_index():
                            files_to_index.append((file_path, lang, code))

        orchestrator.process_files(files_to_index)
        
        cls.verifier = RelationshipVerifier(cls.db_service)


class AutoDebugTestResult(unittest.TextTestResult):
    """A custom TestResult to inject logic on failure."""

    def _trigger_auto_debug(self, test):
        """Extracts symbol and re-runs the indexer with debug info."""
        if not (TestLanguageSupportSuite.auto_debug and self.failfast):
            return

        symbols_to_debug = []
        if hasattr(test, 'relationship_data'):
            rel = test.relationship_data
            symbols_to_debug.extend([rel['source'], rel['target']])

        if symbols_to_debug:
            lang_name = test.language_name
            debug_symbols_str = ", ".join(symbols_to_debug)
            print(f"\n--- Auto-debugging failed test: {test.id()} ---")
            print(f"--- Re-running indexer with logging on symbols=[{debug_symbols_str}] for language {lang_name} ---\n")
            
            TestLanguageSupportSuite.debug_options.symbol_names = symbols_to_debug
            TestLanguageSupportSuite.debug_options.language = lang_name
            TestLanguageSupportSuite.rebuild_index()
        else:
            print(f"\n--- Could not determine symbols for auto-debugging test: {test.id()} ---")

    def addFailure(self, test, err):
        self._trigger_auto_debug(test)
        super().addFailure(test, err)

    def addError(self, test, err):
        self._trigger_auto_debug(test)
        super().addError(test, err)


class AutoDebugTestRunner(unittest.TextTestRunner):
    """A custom test runner that uses our custom result class."""
    def _makeResult(self):
        """This is the key change to use our custom result object."""
        return AutoDebugTestResult(self.stream, self.descriptions, self.verbosity)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    
    language_to_test = TestLanguageSupportSuite.language_to_test

    definitions_path = os.path.join(os.path.dirname(__file__), 'lang_definitions')
    for filename in os.listdir(definitions_path):
        if filename.endswith('.py') and not filename.startswith('__') and not filename.startswith('base_'):
            module_name = f"test.lang_definitions.{filename[:-3]}"
            module = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BaseTestDefinition) and obj is not BaseTestDefinition:
                    definition_instance = obj()

                    if language_to_test and definition_instance.language_name != language_to_test:
                        continue
                    
                    class_name = f"Test_{definition_instance.language_name.capitalize()}"
                    DynamicTestClass = type(class_name, (TestLanguageSupportSuite,), {})

                    for rel in definition_instance.get_expected_relationships():
                        if rel['type'] in definition_instance.supported_relationships:
                            def test_method(self, rel=rel, lang=definition_instance.language_name):
                                self.language_name = lang
                                self.relationship_data = rel
                                # First, verify both symbols exist
                                self.verifier.assert_symbol_exists(rel['source'], lang, rel.get('source_qname'))
                                self.verifier.assert_symbol_exists(rel['target'], lang, rel.get('target_qname'))
                                
                                # Then, verify the relationship
                                self.verifier.assert_relationship(
                                    rel['source'],
                                    rel['target'],
                                    rel['type'],
                                    lang,
                                    rel.get('count', 1),
                                    rel.get('source_qname'),
                                    rel.get('target_qname')
                                )
                            
                            test_name = f"test_{definition_instance.language_name}_{rel['type']}_{rel['source']}_to_{rel['target']}"
                            setattr(DynamicTestClass, test_name, test_method)
                    
                    for member_name, member_obj in inspect.getmembers(definition_instance):
                        if member_name.startswith('test_') and inspect.isfunction(member_obj):
                            def custom_test_method(self, member_obj=member_obj, definition_instance=definition_instance):
                                member_obj(self, definition_instance)
                            
                            custom_test_name = f"test_{definition_instance.language_name}_custom_{member_name}"
                            setattr(DynamicTestClass, custom_test_name, custom_test_method)
                    
                    suite.addTests(loader.loadTestsFromTestCase(DynamicTestClass))

    return suite

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Language Support Test Suite")
    parser.add_argument(
        '--language',
        help="Run tests for a single language (e.g., 'python', 'javascript')"
    )
    parser.add_argument(
        '--auto-debug',
        type=lambda x: (str(x).lower() == 'true'),
        default=True,
        help="Automatically re-run failed tests with debug symbols (default: True)"
    )
    parser.add_argument(
        '-f', '--failfast',
        action='store_true',
        help="Stop on first fail or error"
    )
    
    args, remaining_argv = parser.parse_known_args()
    
    if args.language:
        TestLanguageSupportSuite.language_to_test = args.language

    TestLanguageSupportSuite.auto_debug = args.auto_debug
    TestLanguageSupportSuite.fail_fast = args.failfast

    sys.argv = [sys.argv[0]] + remaining_argv
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = AutoDebugTestRunner(failfast=args.failfast)
    result = runner.run(suite)

    if not result.wasSuccessful():
        sys.exit(1)

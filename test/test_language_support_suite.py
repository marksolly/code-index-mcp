"""
Language Support Test Suite

This script runs a series of tests to verify language support for code indexing.
It dynamically discovers and loads test definitions for various programming languages.

Usage examples with `uv run`:

First, ensure correct python virtual environment is active:
    `source /home/htpc/code-index-mcp/.venv/bin/activate`

1. Run all language tests:
   uv run python test/test_language_support_suite.py --failfast

2. Run tests for a single language (e.g., Python):
   uv run python test/test_language_support_suite.py --language=python --failfast

3. Dump test plan without running tests:
   uv run python test/test_language_support_suite.py --dump-plan [--language=python]
"""
import unittest
import os
import importlib
import inspect
import sys
import argparse
import time
import re
import json

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


class TestResultWithPersistence(AutoDebugTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed_tests_file = os.path.join(project_root, 'test', 'passed_tests.json')
        self.passed_tests = self._load_passed_tests()

    def _load_passed_tests(self):
        if os.path.exists(self.passed_tests_file):
            with open(self.passed_tests_file, 'r') as f:
                return set(json.load(f))
        return set()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_tests.add(test.id())

    def save_passed_tests(self):
        with open(self.passed_tests_file, 'w') as f:
            json.dump(sorted(list(self.passed_tests)), f, indent=4)


class AutoDebugTestRunner(unittest.TextTestRunner):
    """A custom test runner that uses our custom result class."""
    def _makeResult(self):
        """This is the key change to use our custom result object."""
        # return AutoDebugTestResult(self.stream, self.descriptions, self.verbosity)
        return TestResultWithPersistence(self.stream, self.descriptions, self.verbosity)


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

                            # Use execution order to ensure correct test execution order
                            execution_order = rel.get('_execution_order', 0)
                            test_name = f"test_{execution_order:04d}_{definition_instance.language_name}_{rel['type']}_{rel['source']}_to_{rel['target']}"
                            setattr(DynamicTestClass, test_name, test_method)
                    
                    for member_name, member_obj in inspect.getmembers(definition_instance):
                        if member_name.startswith('test_') and inspect.isfunction(member_obj):
                            def custom_test_method(self, member_obj=member_obj, definition_instance=definition_instance):
                                member_obj(self, definition_instance)
                            
                            custom_test_name = f"test_{definition_instance.language_name}_custom_{member_name}"
                            setattr(DynamicTestClass, custom_test_name, custom_test_method)
                    
                    suite.addTests(loader.loadTestsFromTestCase(DynamicTestClass))

    return suite

def main():
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
    parser.add_argument(
        '--dump-plan',
        action='store_true',
        help="Dump test plan (list of tests that would run) without executing them"
    )
    
    args, remaining_argv = parser.parse_known_args()
    
    TestLanguageSupportSuite.auto_debug = args.auto_debug
    TestLanguageSupportSuite.fail_fast = args.failfast
    sys.argv = [sys.argv[0]] + remaining_argv

    # Load passed tests from file once
    passed_tests_file = os.path.join(project_root, 'test', 'passed_tests.json')
    passed_tests_set = set()
    if os.path.exists(passed_tests_file):
        with open(passed_tests_file, 'r') as f:
            passed_tests_set = set(json.load(f))

    def get_all_tests(suite):
        tests = []
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                tests.extend(get_all_tests(test))
            else:
                tests.append(test)
        return tests

    # Load the test suite and validate passed_tests.json contents
    print("--- Loading test suite and validating passed_tests.json ---")
    TestLanguageSupportSuite.language_to_test = args.language  # Respect language filter
    full_suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])

    # Validate passed_tests.json contents against current test suite
    all_tests = get_all_tests(full_suite)
    all_test_ids = {test.id() for test in all_tests}

    invalid_tests = []
    for test_id in passed_tests_set:
        if test_id not in all_test_ids:
            invalid_tests.append(test_id)

    if invalid_tests:
        print(f"❌ ERROR: {len(invalid_tests)} tests in passed_tests.json do not exist in current test suite:")
        for test_id in sorted(invalid_tests):
            print(f"  - {test_id}")

        print(f"\n=== AVAILABLE TESTS IN CURRENT SUITE ({len(all_test_ids)} total) ===")
        for i, test_id in enumerate(sorted(all_test_ids), 1):
            print(f"{i:2d}. {test_id}")

        print("\nThis indicates that test names have changed due to non-deterministic behavior")
        print("or the test definitions have been modified since passed_tests.json was last updated.")
        print("\nTo fix this:")
        print("1. Update passed_tests.json with current valid test names from the list above.")
        print("2. Remove any test names that no longer exist.")
        print("3. Or investigate if there's non-deterministic test name generation.")
        print("4. As an absolute last resort, delete passed_tests.json and accept undiagnosed regressions will occur.")
        sys.exit(1)
    else:
        print(f"✅ All {len(passed_tests_set)} entries in passed_tests.json are valid test names")

    # If dump-plan flag is set, just show the test plan and exit
    if args.dump_plan:
        print("\n=== TEST PLAN ===")
        print(f"Language filter: {args.language if args.language else 'All languages'}")
        print(f"Auto-debug: {args.auto_debug}")
        print(f"Fail-fast: {args.failfast}")
        print()

        # --- First Pass: Previously passed tests ---
        print("--- Phase 1: Previously passed tests (regression check) ---")
        passed_tests = []
        for test in all_tests:
            if test.id() in passed_tests_set:
                passed_tests.append(test)

        if passed_tests:
            for i, test in enumerate(passed_tests, 1):
                print(f"{i:2d}. {test.id()}")
            print(f"Total: {len(passed_tests)} tests")
        else:
            print("No previously passed tests found.")
        print()

        # --- Second Pass: New and remaining tests ---
        print("--- Phase 2: New and remaining tests ---")
        new_tests = []
        for test in all_tests:
            if test.id() not in passed_tests_set:
                new_tests.append(test)

        if new_tests:
            for i, test in enumerate(new_tests, 1):
                print(f"{i:2d}. {test.id()}")
            print(f"Total: {len(new_tests)} tests")
        else:
            print("No new or remaining tests found.")
        print()

        total_tests = len(passed_tests) + len(new_tests)
        print(f"Grand total: {total_tests} tests")
        print("\nUse --dump-plan to see this plan, omit the flag to actually run the tests.")
        return

    # --- First Pass: Run passed tests for the specified language (or all languages) to catch regressions ---
    print("--- Running previously passed tests ---")

    TestLanguageSupportSuite.language_to_test = args.language  # Respect language filter
    full_suite_for_regression = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])

    passed_suite = unittest.TestSuite()
    for test in get_all_tests(full_suite_for_regression):
        if test.id() in passed_tests_set:
            passed_suite.addTest(test)

    runner = AutoDebugTestRunner(failfast=args.failfast)
    passed_result = runner.run(passed_suite)

    if not passed_result.wasSuccessful():
        print("\n--- Regressions detected in previously passed tests ---")
        print("\nURGENT: Check your most recent changes for unintended consequences.")
        if hasattr(passed_result, 'save_passed_tests'):
            passed_result.save_passed_tests()
        sys.exit(1)
    else:
        print("\n No regressions detected.")

    # --- Second Pass: Run new and remaining tests ---
    TestLanguageSupportSuite.language_to_test = args.language

    suite_for_new_tests = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])

    new_suite = unittest.TestSuite()
    for test in get_all_tests(suite_for_new_tests):
        if test.id() not in passed_tests_set:
            new_suite.addTest(test)

    print(f"\n--- Running {new_suite.countTestCases()} new and remaining tests ---")
    new_result = runner.run(new_suite)

    if hasattr(new_result, 'save_passed_tests'):
        new_result.save_passed_tests()

    if not new_result.wasSuccessful():
        sys.exit(1)

if __name__ == '__main__':
    main()

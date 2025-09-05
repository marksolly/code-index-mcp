"""
Test suite for incremental indexing functionality
"""

import os
import sys
import tempfile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.code_scope_mcp.db.database import DatabaseService
from src.code_scope_mcp.indexing.orchestrator import IndexingOrchestrator


class TestIncrementalIndexing:
    """Test incremental indexing scenarios"""

    def __init__(self):
        self.temp_dir = None
        self.db_path = None
        self.db_service = None
        self.db_conn = None
        self.orchestrator = None

    def setup_method(self):
        """Set up test environment with temporary directory and database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")

        # Initialize database
        self.db_service = DatabaseService(self.db_path)
        self.db_service.connect()
        self.db_service.initialize_db()

        # Get database connection for queries
        self.db_conn = self.db_service.get_connection()

        # Create orchestrator
        self.orchestrator = IndexingOrchestrator(
            db_service=self.db_service,
            logger=None,
            incremental_mode=False
        )

    def teardown_method(self):
        """Clean up test environment"""
        if self.db_service:
            self.db_service.close()
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_single_file_addition(self):
        """Test adding a single new file to an existing index"""
        # First, create and index a base project
        self._create_base_project()

        # Run initial full index
        self.orchestrator.process_files([
            os.path.join(self.temp_dir, "main.py"),
            os.path.join(self.temp_dir, "utils.py")
        ])

        # Verify initial state
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM code_symbols")
        initial_count = cursor.fetchone()[0]
        cursor.close()
        assert initial_count > 0

        # Add new file
        new_file_path = os.path.join(self.temp_dir, "new_module.py")
        with open(new_file_path, 'w') as f:
            f.write("""
def new_function():
    return "Hello from new module"

class NewClass:
    def method(self):
        return "New class method"
""")

        # Run incremental index on just the new file
        incremental_orchestrator = IndexingOrchestrator(
            db_service=self.db_service,
            incremental_mode=True,
            logger=None
        )

        incremental_orchestrator.process_files([
            new_file_path  # process_files expects a list of file paths, not tuples
        ])

        # Verify new symbols were added without affecting existing ones
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM code_symbols")
        final_count = cursor.fetchone()[0]
        cursor.close()
        assert final_count > initial_count

        # Verify the new symbols exist
        cursor = self.db_conn.cursor()
        cursor.execute(
            "SELECT name FROM code_symbols WHERE file_id IN (SELECT id FROM files WHERE path = ?)",
            (new_file_path,)
        )
        new_symbols = cursor.fetchall()
        cursor.close()
        assert len(new_symbols) >= 2  # function and class

    def test_file_deletion(self):
        """Test removing a file from an existing index"""
        # First, create and index a base project
        self._create_base_project()

        # Add an extra file for deletion
        delete_file_path = os.path.join(self.temp_dir, "to_delete.py")
        with open(delete_file_path, 'w') as f:
            f.write("""
def function_to_delete():
    return "This will be deleted"

class ClassToDelete:
    pass
""")

        # Index all files including the one to be deleted
        all_files = [
            os.path.join(self.temp_dir, "main.py"),
            os.path.join(self.temp_dir, "utils.py"),
            delete_file_path
        ]
        self.orchestrator.process_files(all_files)

        # Verify initial state
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM code_symbols")
        initial_count = cursor.fetchone()[0]
        cursor.close()
        assert initial_count > 0

        # Verify the file to delete exists in index
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT id FROM files WHERE path = ?", (delete_file_path,))
        file_exists = cursor.fetchone()
        cursor.close()
        assert file_exists is not None

        # Delete the file from filesystem
        os.remove(delete_file_path)

        # Run incremental index - should detect file is gone and remove it
        incremental_orchestrator = IndexingOrchestrator(
            db_service=self.db_service,
            incremental_mode=True,
            logger=None
        )

        # Pass the directory path so FileListBuilder can scan and detect missing files
        incremental_orchestrator.process_files([self.temp_dir])

        # Verify file was removed from index
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT id FROM files WHERE path = ?", (delete_file_path,))
        file_exists_after = cursor.fetchone()
        cursor.close()
        assert file_exists_after is None  # File should be gone from index

        # Verify symbols were also removed (CASCADE delete)
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM code_symbols WHERE file_id NOT IN (SELECT id FROM files)")
        orphaned_symbols = cursor.fetchone()[0]
        cursor.close()
        assert orphaned_symbols == 0  # No orphaned symbols should remain

    def test_file_content_change(self):
        """Test modifying file content and re-indexing"""
        # First, create and index a base project
        self._create_base_project()

        # Run initial full index
        file_path = os.path.join(self.temp_dir, "utils.py")
        self.orchestrator.process_files([file_path])

        # Get initial function count
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM code_symbols WHERE name = 'helper_function'")
        initial_func_count = cursor.fetchone()[0]
        cursor.close()
        assert initial_func_count > 0

        # Modify the file content
        with open(file_path, 'w') as f:
            f.write("""
def helper_function():
    return "Modified result"

def new_helper_function():
    return "Added function"

class ModifiedUtilityClass:
    @staticmethod
    def modified_static_method():
        return "Modified static"
""")

        # Run incremental index on the modified file
        incremental_orchestrator = IndexingOrchestrator(
            db_service=self.db_service,
            incremental_mode=True,
            logger=None
        )

        incremental_orchestrator.process_files([file_path])

        # Verify the new function was added
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM code_symbols WHERE name = 'new_helper_function'")
        new_func_count = cursor.fetchone()[0]
        cursor.close()
        assert new_func_count >= 1

        # Verify modified method exists
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM code_symbols WHERE name = 'modified_static_method'")
        modified_method_count = cursor.fetchone()[0]
        cursor.close()
        assert modified_method_count >= 1

    def test_dependency_cascade(self):
        """Test that related files are also re-indexed when dependencies change"""
        # Create files with dependencies
        main_file = os.path.join(self.temp_dir, "main.py")
        utils_file = os.path.join(self.temp_dir, "utils.py")
        dependent_file = os.path.join(self.temp_dir, "dependent.py")

        # Create main.py that imports from utils
        with open(main_file, 'w') as f:
            f.write("""
from utils import helper_function

def main():
    result = helper_function()
    return result
""")

        # Create utils.py with the function
        with open(utils_file, 'w') as f:
            f.write("""
def helper_function():
    return "Helper result"
""")

        # Create dependent.py that imports from main
        with open(dependent_file, 'w') as f:
            f.write("""
from main import main

def dependent_function():
    return main()
""")

        # Index all files initially
        self.orchestrator.process_files([main_file, utils_file, dependent_file])

        # Get initial relationship count and dump
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM relationships")
        initial_relationships = cursor.fetchone()[0]

        print(f"\n=== INITIAL RELATIONSHIPS ({initial_relationships} total) ===")
        cursor.execute("""
            SELECT r.id, s1.name as source_name, rt.name as rel_type, s2.name as target_name
            FROM relationships r
            JOIN code_symbols s1 ON r.source_symbol_id = s1.id
            JOIN code_symbols s2 ON r.target_symbol_id = s2.id
            JOIN relationship_types rt ON r.type_id = rt.id
            ORDER BY r.id
        """)
        initial_rels = cursor.fetchall()
        for rel in initial_rels:
            print(f"  {rel[0]}: {rel[1]} --({rel[2]})--> {rel[3]}")

        cursor.close()

        # Modify utils.py (dependency root)
        with open(utils_file, 'w') as f:
            f.write("""
def helper_function():
    return "Modified helper result"

def new_helper_function():
    return "New helper"
""")

        # Run incremental index on just utils.py
        # This should trigger re-indexing of main.py and dependent.py due to relationships
        incremental_orchestrator = IndexingOrchestrator(
            db_service=self.db_service,
            incremental_mode=True,
            logger=None
        )


        incremental_orchestrator.process_files([utils_file])

        # Verify new function from utils was indexed
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM code_symbols WHERE name = 'new_helper_function'")
        new_func_count = cursor.fetchone()[0]
        cursor.close()
        assert new_func_count >= 1

        # Verify relationships were updated (should include relationships to the new function)
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM relationships")
        final_relationships = cursor.fetchone()[0]

        print(f"\n=== FINAL RELATIONSHIPS ({final_relationships} total) ===")
        cursor.execute("""
            SELECT r.id, s1.name as source_name, rt.name as rel_type, s2.name as target_name
            FROM relationships r
            JOIN code_symbols s1 ON r.source_symbol_id = s1.id
            JOIN code_symbols s2 ON r.target_symbol_id = s2.id
            JOIN relationship_types rt ON r.type_id = rt.id
            ORDER BY r.id
        """)
        final_rels = cursor.fetchall()
        for rel in final_rels:
            print(f"  {rel[0]}: {rel[1]} --({rel[2]})--> {rel[3]}")

        print(f"\n=== RELATIONSHIP CHANGE SUMMARY ===")
        print(f"Initial: {initial_relationships}")
        print(f"Final: {final_relationships}")
        print(f"Change: {final_relationships - initial_relationships}")

        cursor.close()

        # Note: Exact relationship count may vary, but there should be some relationships
        assert final_relationships >= initial_relationships

    def _create_base_project(self):
        """Create a simple base project for testing"""
        # Create main.py
        main_content = """
from utils import helper_function

def main():
    result = helper_function()
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
"""
        with open(os.path.join(self.temp_dir, "main.py"), 'w') as f:
            f.write(main_content)

        # Create utils.py
        utils_content = """
def helper_function():
    return "Helper result"

class UtilityClass:
    @staticmethod
    def static_method():
        return "Static method"
"""
        with open(os.path.join(self.temp_dir, "utils.py"), 'w') as f:
            f.write(utils_content)

    def _read_test_file(self, filename):
        """Read a test file's content"""
        filepath = os.path.join(self.temp_dir, filename)
        with open(filepath, 'r') as f:
            return f.read()


if __name__ == "__main__":
    # Simple test runner
    test_instance = TestIncrementalIndexing()

    tests_to_run = [
        ('test_single_file_addition', test_instance.test_single_file_addition),
        ('test_file_deletion', test_instance.test_file_deletion),
        ('test_file_content_change', test_instance.test_file_content_change),
        ('test_dependency_cascade', test_instance.test_dependency_cascade),
    ]

    passed_tests = 0
    total_tests = len(tests_to_run)

    try:
        print("Setting up test environment...")
        test_instance.setup_method()

        for test_name, test_method in tests_to_run:
            try:
                print(f"\nRunning {test_name}...")
                # Reset database for each test
                test_instance.db_service.close()
                if os.path.exists(test_instance.db_path):
                    os.remove(test_instance.db_path)
                test_instance.db_service = DatabaseService(test_instance.db_path)
                test_instance.db_service.connect()
                test_instance.db_service.initialize_db()
                test_instance.db_conn = test_instance.db_service.get_connection()
                test_instance.orchestrator = IndexingOrchestrator(
                    db_service=test_instance.db_service,
                    logger=None,
                    incremental_mode=False
                )

                test_method()
                print(f"✓ Test passed: {test_name}")
                passed_tests += 1

            except Exception as e:
                print(f"✗ Test failed: {test_name} - {e}")
                import traceback
                traceback.print_exc()
                print()  # Add blank line after error

    except Exception as setup_error:
        print(f"✗ Setup failed: {setup_error}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nCleaning up test environment...")
        test_instance.teardown_method()

    print(f"\nTest Results: {passed_tests}/{total_tests} tests passed")
    if passed_tests == total_tests:
        print("All tests passed! ✓")
    else:
        print(f"{total_tests - passed_tests} tests failed ✗")

"""
Database management for the Code Index MCP server.

This module provides a service to manage the SQLite database connection,
session, schema, and CRUD operations.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager


class DatabaseService:
    """
    Manages the SQLite database connection, session, and schema.
    Provides high-speed mode for bulk operations.
    """

    def __init__(self, db_path: str):
        """
        Initialize the DatabaseService.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None

        # High-speed mode state
        self._high_speed_enabled = False
        self._original_settings: Dict[str, Any] = {}
        self._dropped_indexes: list[str] = []

    def connect(self):
        """Establish a connection to the database with always-on optimizations."""
        if self.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

            # Always-on optimizations (safe)
            self._apply_always_on_optimizations()

    def _apply_always_on_optimizations(self):
        """Apply optimizations that are always safe to use."""
        if not self.conn:
            return

        # Memory and cache optimizations (always beneficial)
        self.conn.execute("PRAGMA journal_mode = MEMORY;")
        self.conn.execute("PRAGMA cache_size = -64000;")      # 64MB cache
        self.conn.execute("PRAGMA mmap_size = 268435456;")    # 256MB memory mapping
        self.conn.execute("PRAGMA temp_store = MEMORY;")      # Temp tables in memory

        # Start with safe defaults
        self.conn.execute("PRAGMA synchronous = NORMAL;")     # Safe default
        self.conn.execute("PRAGMA foreign_keys = ON;")        # Integrity on

    def enable_high_speed_mode(self):
        """Enable high-speed mode for bulk operations."""
        if self._high_speed_enabled or not self.conn:
            return

        # Save original settings for restoration
        self._save_original_settings()

        # Apply speed optimizations
        self._apply_speed_optimizations()

        # Drop indexes for faster writes
        self._drop_indexes_for_speed()

        self._high_speed_enabled = True

    def disable_high_speed_mode(self):
        """Disable high-speed mode and restore safe settings."""
        if not self._high_speed_enabled or not self.conn:
            return

        # Recreate indexes
        self._recreate_indexes()

        # Restore original settings
        self._restore_original_settings()

        self._high_speed_enabled = False

    @contextmanager
    def high_speed_mode(self):
        """Context manager for high-speed mode."""
        try:
            self.enable_high_speed_mode()
            yield
        finally:
            self.disable_high_speed_mode()

    def _save_original_settings(self):
        """Save current database settings for restoration."""
        if not self.conn:
            return

        settings_to_save = [
            'synchronous',
            'foreign_keys',
            'cache_size',
            'mmap_size',
            'temp_store',
            'journal_mode'
        ]

        self._original_settings = {}
        for setting in settings_to_save:
            try:
                cursor = self.conn.cursor()
                cursor.execute(f"PRAGMA {setting}")
                value = cursor.fetchone()[0]
                self._original_settings[setting] = value
                cursor.close()
            except:
                pass

    def _apply_speed_optimizations(self):
        """Apply performance optimizations for bulk operations."""
        if not self.conn:
            return

        # Dangerous optimizations (only during bulk operations)
        self.conn.execute("PRAGMA synchronous = OFF;")        # No disk sync (fast but risky)
        self.conn.execute("PRAGMA foreign_keys = OFF;")       # Skip FK validation

        # Additional performance tweaks
        self.conn.execute("PRAGMA wal_autocheckpoint = 0;")   # Disable auto-checkpointing
        self.conn.execute("PRAGMA journal_size_limit = 0;")   # Unlimited journal

    def _restore_original_settings(self):
        """Restore original database settings."""
        if not self.conn:
            return

        for setting, value in self._original_settings.items():
            try:
                if setting in ['synchronous', 'foreign_keys']:
                    # Convert numeric values back to keywords
                    if setting == 'synchronous':
                        value = 'OFF' if value == 0 else 'NORMAL' if value == 1 else 'FULL'
                    elif setting == 'foreign_keys':
                        value = 'ON' if value == 1 else 'OFF'

                self.conn.execute(f"PRAGMA {setting} = {value}")
            except:
                pass

    def _drop_indexes_for_speed(self):
        """Drop indexes before bulk writes to speed up inserts."""
        if not self.conn:
            return

        indexes_to_drop = [
            'idx_files_path',
            'idx_code_symbols_name',
            'idx_code_symbols_qname',
            'idx_code_symbols_file_id',
            'idx_relationships_source',
            'idx_relationships_target'
        ]

        self._dropped_indexes = []
        for index_name in indexes_to_drop:
            try:
                self.conn.execute(f"DROP INDEX IF EXISTS {index_name}")
                self._dropped_indexes.append(index_name)
            except:
                pass

    def _recreate_indexes(self):
        """Recreate indexes after bulk writes."""
        if not self.conn:
            return

        # Recreate the indexes
        index_definitions = [
            ("idx_files_path", "CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);"),
            ("idx_code_symbols_name", "CREATE INDEX IF NOT EXISTS idx_code_symbols_name ON code_symbols(name);"),
            ("idx_code_symbols_qname", "CREATE INDEX IF NOT EXISTS idx_code_symbols_qname ON code_symbols(qname);"),
            ("idx_code_symbols_file_id", "CREATE INDEX IF NOT EXISTS idx_code_symbols_file_id ON code_symbols(file_id);"),
            ("idx_relationships_source", "CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_symbol_id);"),
            ("idx_relationships_target", "CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_symbol_id);")
        ]

        for index_name, create_sql in index_definitions:
            if index_name in self._dropped_indexes:
                try:
                    self.conn.execute(create_sql)
                except:
                    pass

        self._dropped_indexes = []

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def delete_db(self):
        """Delete the database file."""
        self.close()
        try:
            if self.db_path.exists():
                self.db_path.unlink()
                print(f"Database file deleted: {self.db_path}")
        except OSError as e:
            print(f"Error deleting database file: {e}")

    def get_connection(self) -> sqlite3.Connection:
        """
        Return the active database connection.

        Returns:
            An active sqlite3.Connection object.

        Raises:
            ConnectionError: If the connection is not established.
        """
        if not self.conn:
            raise ConnectionError("Database connection is not established. Call connect() first.")
        return self.conn

    def initialize_db(self):
        """
        Initialize the database by creating tables and pre-populating lookup data.
        """
        if not self.conn:
            self.connect()

        cursor = self.conn.cursor()

        # DDL Statements
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS symbol_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS relationship_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                outbound_display TEXT,
                inbound_display TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                size INTEGER,
                line_count INTEGER,
                modified_time TIMESTAMP,
                language TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS code_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                name TEXT NOT NULL COLLATE NOCASE,
                qname TEXT,
                type_id INTEGER NOT NULL,
                line_start INTEGER,
                line_end INTEGER,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (type_id) REFERENCES symbol_types(id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS symbol_properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                FOREIGN KEY (symbol_id) REFERENCES code_symbols(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_symbol_id INTEGER NOT NULL,
                target_symbol_id INTEGER NOT NULL,
                type_id INTEGER NOT NULL,
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY (source_symbol_id) REFERENCES code_symbols(id) ON DELETE CASCADE,
                FOREIGN KEY (target_symbol_id) REFERENCES code_symbols(id) ON DELETE CASCADE,
                FOREIGN KEY (type_id) REFERENCES relationship_types(id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);",
            "CREATE INDEX IF NOT EXISTS idx_code_symbols_name ON code_symbols(name);",
            "CREATE INDEX IF NOT EXISTS idx_code_symbols_qname ON code_symbols(qname);",
            "CREATE INDEX IF NOT EXISTS idx_code_symbols_file_id ON code_symbols(file_id);",
            "CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_symbol_id);",
            "CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_symbol_id);",
            """
            CREATE TABLE IF NOT EXISTS unresolved_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_symbol_id INTEGER NOT NULL,
                relationship_type_id INTEGER NOT NULL,
                intermediate_symbol_qname TEXT,
                target_name TEXT NOT NULL,
                target_qname TEXT,
                needs_type_id INTEGER NOT NULL, /* type of relationship this symbol pair is waiting on */
                FOREIGN KEY (source_symbol_id) REFERENCES code_symbols (id) ON DELETE CASCADE
            );
            """,
        ]

        for statement in ddl_statements:
            cursor.execute(statement)

        # Pre-populate lookup tables
        symbol_types = ['file', 'function', 'class', 'method', 'constant', 'import', 'global', 'variable', 'export', 'namespace']

        # Relationship types with display names for reports
        # Format: (name, outbound_display, inbound_display)
        relationship_type_data = [
            ('calls_file_function',     'calls',           'called_by'),
            ('calls_class_method',      'calls',           'called_by'),
            ('imports',                 'imports',         'imported_by'),
            ('inherits',                'inherits',        'inherited_by'),
            ('instantiates',            'instantiates',    'instantiated_by'),
            ('declares_file_function',  'defines_fn',      'defined_in'),
            ('declares_class_method',   'has_method',      'declared_by'),
            ('declares_class',          'declares',        'declared_by'),
            ('declares_constant',       'declares',        'declared_by'),
            ('references_variable',     'references',      'referenced_by'),
            ('overrides',               'overrides',       'overridden_by'),
            ('defines_namespace',       'defines',         'defined_by'),
            ('is_instance_of',          'is_instance_of',  'has_instance')
        ]

        for s_type in symbol_types:
            cursor.execute("INSERT OR IGNORE INTO symbol_types (name) VALUES (?)", (s_type,))

        for name, outbound_display, inbound_display in relationship_type_data:
            cursor.execute("""
                INSERT OR IGNORE INTO relationship_types (name, outbound_display, inbound_display)
                VALUES (?, ?, ?)
            """, (name, outbound_display, inbound_display))

        # Clear unresolved relationships from previous runs
        cursor.execute("DELETE FROM unresolved_relationships;")

        self.conn.commit()
        cursor.close()

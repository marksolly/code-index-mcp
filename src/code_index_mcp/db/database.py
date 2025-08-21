"""
Database management for the Code Index MCP server.

This module provides a service to manage the SQLite database connection,
session, schema, and CRUD operations.
"""

import sqlite3
from pathlib import Path
from typing import Optional


class DatabaseService:
    """
    Manages the SQLite database connection, session, and schema.
    """

    def __init__(self, db_path: str):
        """
        Initialize the DatabaseService.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """Establish a connection to the database."""
        if self.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode = MEMORY;")

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
                name TEXT NOT NULL UNIQUE
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
        symbol_types = ['file', 'function', 'class', 'constant', 'import', 'global', 'variable', 'export', 'namespace']
        relationship_types = ['calls', 'imports', 'inherits', 'instantiates', 'declares_file_function', 'declares_class_method', 'declares_class', 'declares_constant', 'references_variable', 'overrides', 'defines_namespace', 'is_instance_of']

        for s_type in symbol_types:
            cursor.execute("INSERT OR IGNORE INTO symbol_types (name) VALUES (?)", (s_type,))

        for r_type in relationship_types:
            cursor.execute("INSERT OR IGNORE INTO relationship_types (name) VALUES (?)", (r_type,))

        # Clear unresolved relationships from previous runs
        cursor.execute("DELETE FROM unresolved_relationships;")

        self.conn.commit()
        cursor.close()

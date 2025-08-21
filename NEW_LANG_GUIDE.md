# Developer's Guide to Adding a New Language

This guide walks you through adding support for a new language to the code indexer. The architecture is a **phased, strategy-driven pipeline** designed to be highly modular and extensible. You'll add new languages by creating small, focused "analyzer" components that plug into this pipeline.

The process is entirely test-driven. You will first create tests and code samples, then implement the logic to make the tests pass.

## Static Analysis Philosophy

It is bordering on impossible to create a 100% concrete graph of relationships in a codebase without actually executing the code or creating elaborate lookups for every edge case. Therefore, we take a fail-soft approach that is accepting of some ambiguity, while being "good enough" for the mission of uncovering relationships and summarising dependencies.

## The Indexing Pipeline: A Quick Overview

The indexing process happens in three phases:

1.  **Phase 1: Symbol Extraction**: In this phase, a language-specific `SymbolExtractor` parses every file using `tree-sitter`. It identifies all primary symbols (classes, functions, etc.), constructs their qualified names (`qnames`), and records them. It also creates **first-order relationships** (those that can be determined directly from the file's syntax, like a class containing a method) and notes down any relationships that can't be figured out immediately in an `unresolved_relationships` table. This phase must complete for all files before Phase 2 begins.

2.  **Phase 2: Intermediate Resolution**: After all symbols are known, a series of `RelationshipAnalyzer` classes run. They look at the `unresolved_relationships` table and try to solve the easy ones, like connecting an `import` statement to the file it imports, or a variable's type hint to a class definition in the same file.

3.  **Phase 3: Final Relationship Resolution**: This final phase handles complex, multi-step resolutions. For example, to figure out where `my_var.method()` points, it first needs to find the type of `my_var` (resolved in Phase 2) and then find `method` on that type.

Not all relationships require all three phases. Many can be fully resolved in Phase 2; Phase 3 is reserved for those that depend on the relationships built during the second phase.

---

## Qualified Names (qnames): The Standard

A core concept is the **qualified name (`qname`)**. It's a more specific, context-aware name for a symbol that helps resolve ambiguity. While a simple `name` like `GetUser` could appear in many files, a `qname` provides a more precise identifier, without being globally unique.

Because of the inherent challenge of static analysis, this system is designed to be accepting of some ambiguity.

**The Standard Format:** `<enclosing_scope>(:.)<symbol_name>`

A qualified name must only have two parts. The separator (`:` or `.`) depends on enclosing scope type. Use `.` for object-oriented contexts (class methods) and `:` for file-level contexts (functions in a file).

### Examples of Correctly Formed Qnames:

-   **Function in a file**: `my_utils.py:calculate`
-   **Class in a file**: `my_models.py:User`
-   **Method in a class**: `User.get_profile`
-   **File itself**: `my_utils.py` (When the file is the symbol, the file name is the qname).

### Examples of Incorrectly Formed Qnames:

-   `my_models.py:User.get_profile` (Incorrect: Contains three parts. The filename should not be included for class methods.)

**Important**: `qnames` are intended to be reasonably identifying, but not guaranteed to be 100% unique and ambiguity is permitted. They are the primary tool for looking up symbols, but the system's final source of truth is the symbol's integer ID in the database.

---

## Step 1: Define the Language Definition

Before creating tests, you must define the language's core properties by creating a `LanguageDefinition` class. This class tells the indexer which symbol and relationship types are supported for your language, preventing invalid data from being indexed.

-   **Location**: `src/code_index_mcp/indexing/languages.py`
-   **Action**: Create a new class that inherits from `LanguageDefinition` and implement the abstract properties.

### Example: `GoLanguageDefinition`

```python
# src/code_index_mcp/indexing/languages.py
from typing import List
from .languages import LanguageDefinition

class GoLanguageDefinition(LanguageDefinition):
    @property
    def language_name(self) -> str:
        return "go"

    @property
    def supported_symbol_types(self) -> List[str]:
        return [
            "struct",
            "method",
            "function",
            "module",
        ]

    @property
    def supported_relationship_types(self) -> List[str]:
        return [
            "contains_method",
            "instantiates",
            "calls",
            "imports",
        ]
```

### Why is this important?

The `IndexWriter` uses this definition to validate every symbol and relationship it receives. If you attempt to add a symbol or relationship with a type that is not in these lists, the `IndexWriter` will log a warning and discard it. This ensures data integrity and helps you catch errors early in the development process.

---

## Step 2: Create the Test Environment

Before writing any logic, set up the test case for your new language (e.g., "Go").

1.  **Add Code Samples**: Create a directory `test/small-samples/go/`. Add small `.go` files that contain clear examples of the language features you want to index.
2.  **Create a Test Definition**: Create `test/lang_definitions/go.py`. In it, define a `GoTestDefinition` class inheriting from `BaseTestDefinition`.
3.  **Define Expected Relationships**: In your `GoTestDefinition`, create a method `get_expected_relationships` that returns a list of all relationships you expect to find. This defines correctness.
4.  **Enable Relationships Incrementally**: Your `GoTestDefinition` must also have a `supported_relationships` list. The test runner will *only* run tests for the relationship types in this list. To follow a Test-Driven Development (TDD) approach:
    a. Define all expected relationships in `get_expected_relationships`.
    b. Comment out all but one relationship type in the `supported_relationships` list.
    c. Implement the logic for that one relationship until the test passes.
    d. Uncomment the next relationship type and repeat.

### Step 2a: Example Test Definition

Here is a realistic example of what the `test/lang_definitions/go.py` file would look like, based on the structure of existing tests.

```python
# test/lang_definitions/go.py
from typing import List, Dict, Any
from .base_test_definition import BaseTestDefinition

class GoTestDefinition(BaseTestDefinition):
    @property
    def language_name(self) -> str:
        return "go"

    @property
    def supported_relationships(self) -> List[str]:
        # Start by enabling only one relationship type to test.
        # As you implement analyzers, you will uncomment more.
        return [
            'contains_method',
            'instantiates',
            # 'calls',
        ]

    def get_sample_files(self) -> List[str]:
        return ["test/small-samples/go/main.go"]

    def get_expected_relationships(self) -> List[Dict[str, Any]]:
        """
        Define the ground truth for relationships in the sample Go files.
        """
        return [
            # Test case for the first-order relationship in main.go
            {
                'source_qname': 'main.go:User',
                'target_qname': 'main.go:User.GetProfile',
                'type': 'contains_method'
            },
            # Test case for the instantiation in main.go
            {
                'source_qname': 'main.go:main',
                'target_qname': 'main.go:Car',
                'type': 'instantiates'
            },
        ]
```

### Step 2b: Running the Tests

With your test definition in place, you can run the test suite to see the initial failures. The test runner is the primary tool for validating your implementation.

-   **To run the entire suite for all languages:**
    ```bash
    uv run python test/test_language_support_suite.py --failfast
    ```

-   **To run tests for only your new language (e.g., Go):**
    ```bash
    uv run python test/test_language_support_suite.py --language=go --failfast
    ```

The `--failfast` flag will stop the test run on the first failure, which is useful for focused, iterative development. In addition, when `--failfast` is used it will output additional logging to help diagnose the issue.

### Step 2c: Debugging

When a test fails and `--failfast` is specified, the suite runner provides a detailed log to help you diagnose the issue. Here’s a step-by-step guide to debugging common problems:

1.  **Analyze the Failure**: The traceback will point to the exact assertion that failed. The error message will tell you what relationship was expected and what was actually found (or not found).

2.  **Inspect the Relationship Dump**: The test output includes a (filtered) dump of all incoming and outgoing relationships for the source and target symbols involved in the failed test. This is your primary tool for understanding what the indexer *thinks* is happening.

3.  **Common Issues**:
    *   **Incorrect Relationships**: If a relationship is missing or incorrect, trace back the logic in your `SymbolExtractor` or `RelationshipAnalyzer`. Are you creating the unresolved relationship correctly? Is your analyzer finding the correct target symbol?
    *   **Ambiguous Symbols**: If multiple symbols have the same name, the verifier might be picking the wrong one. This can happen if your analyzer's logic for resolving symbols is too simplistic. For example, an `instantiates` analyzer should prioritize imported symbols over symbols with the same name in other files.
    *   **Qname Mismatches**: Ensure the `qname`s you are creating in your extractor match the format expected by your test definitions.

4.  **Direct Database Inspection**: For complex issues, you can inspect the `test_code_index.db` file directly using a tool like `sqlite3`. This allows you to see the raw data and get a clear picture of what symbols and relationships were created.

5.  **Logging**: If you need more detailed information, you can add more logging to your extractors and analyzers. The `--failfast` flag will re-run the indexer with more verbose logging for the failed test case. You can also temporarily disable symbol filtering in the logger (`IndexingLogger.filters['symbol_names'] = None`) to see all log messages, though this can be noisy.

---

## Step 3: Implement the Symbol Extractor (Phase 1)

The `SymbolExtractor` is the first piece of logic you'll write. It has two jobs:
1.  Identify all symbols in a file.
2.  Identify all **first-order relationships** and **unresolved relationships**.

-   **Location**: `src/code_index_mcp/indexing/symbol_extractors/go_extractor.py`
-   **Tool**: Uses `tree-sitter` for AST parsing. You will need to add `tree-sitter` queries for your language.

### Example: Extracting Symbols and a First-Order Relationship

**Go Code (`test/small-samples/go/main.go`):**
```go
package main

type User struct {}

func (u *User) GetProfile() {
    // ...
}
```

**Extractor Logic (`go_extractor.py`):**
Your extractor runs `tree-sitter` queries to find symbol declarations.

1.  **Extract `User` struct**:
    -   `name`: `User`
    -   `qname`: `test/small-samples/go/main.go:User`
    -   Use `writer.add_symbol()` to record it.

2.  **Extract `GetProfile` method**:
    -   `name`: `GetProfile`
    -   `qname`: `test/small-samples/go:User.GetProfile` (following the standard)
    -   Use `writer.add_symbol()` to record it.

3.  **Create a First-Order Relationship**:
    -   The relationship between the `User` struct and its `GetProfile` method is a **first-order relationship**. It can be fully determined just by looking at this file's AST. You don't need to look up any other symbols.
    -   After adding both symbols, you would immediately call `writer.add_unresolved_relationship()` to create the `contains_method` link between `main.go:User` and `main.go:User.GetProfile`. Although it's resolvable, it's added this way for consistency in the pipeline.

4.  **Handling `instantiates` and `is_instance_of`**:
    -   When an assignment involves a class instantiation (e.g., `my_var = MyClass()`), the extractor should create **two** unresolved relationships:
        1.  An `instantiates` relationship from the enclosing function/method to the class (`MyClass`).
        2.  An `is_instance_of` relationship from the variable (`my_var`) to the class (`MyClass`).
    -   This ensures that the indexer captures both the instantiation event and the type of the resulting variable.

5.  **Create an Unresolved Relationship**: If `GetProfile` called another function, `GetPermissions()`, that would be an unresolved `calls` relationship, because the extractor doesn't know where `GetPermissions` is defined without a wider project view. You would log this in the `unresolved_relationships` table for the analyzers in Phase 2/3 to solve.

6.  **Handling Complex Lookups with `intermediate_symbol_qname`**:
    -   For complex call chains like `my_var.engine.start()`, the extractor cannot directly resolve `start()`. It first needs to know the type of `my_var.engine`.
    -   To handle this, the `add_unresolved_relationship` method accepts an `intermediate_symbol_qname` parameter. The extractor should provide the qname of the intermediate symbol (`my_var.engine` in this case).
    -   A Phase 3 analyzer can then use this information to perform a two-step lookup: first, find the type of `my_var.engine` (which must have been resolved in Phase 2), and then find the `start` method on that type.

---

## Step 4: Implement Relationship Analyzers (Phase 2 & 3)

After you have a working `SymbolExtractor`, you can start implementing `RelationshipAnalyzer` classes. These are responsible for resolving the `unresolved_relationships` logged during Phase 1.

Analyzers are organized into phase-specific directories. This separation is critical because some analyses depend on the results of others.

-   **Principle**: One class, one job. A `GoCallAnalyzer` finds calls, while a `GoImportAnalyzer` resolves imports.
-   **No `tree-sitter`**: Analyzers **do not** parse files. They query the database for symbols and unresolved relationships recorded during Phase 1.

### Phase 2: Intermediate Analyzers

These analyzers resolve foundational relationships that can be determined after all symbols are known. They establish the core structure of the codebase.

-   **Location**: `src/code_index_mcp/indexing/relationship_analyzers/go/phase_2/`
-   **Examples**: `imports`, `inherits`, `is_instance_of`. These relationships typically don't depend on other, more complex relationships.

### Phase 3: Final Analyzers

These analyzers tackle complex relationships that often depend on the results from Phase 2.

-   **Location**: `src/code_index_mcp/indexing/relationship_analyzers/go/phase_3/`
-   **Example**: A `calls` analyzer. To resolve `my_var.method()`, the analyzer first needs to know the type of `my_var`, which was likely determined by an `is_instance_of` analyzer in Phase 2.

The orchestrator ensures all Phase 2 analyzers complete before any Phase 3 analyzers begin.

### The Fallback Mechanism and Confidence Scoring

You don't have to write a language-specific analyzer for every relationship type. The system automatically falls back to a generic implementation.

1.  The orchestrator looks for `GoCallAnalyzer`.
2.  If not found, it looks for `GenericCallAnalyzer` in the `common/` directory.
3.  If neither is found, the relationship is skipped for Go.

You only need to create `go/calls.py` if you need to **override or specialize** the generic logic.

**Improving Generic Analyzers**: If you find a flaw in a generic analyzer, it's better to improve the generic implementation than to create a language-specific workaround. This benefits all languages that use the generic analyzer.

**Confidence Scoring**: The `IndexWriter.add_relationship` method supports a `confidence` parameter (a float between 0.0 and 1.0). This is useful for handling ambiguity. If an analyzer cannot uniquely identify a target symbol, it can create multiple low-confidence relationships. For example, if there are three possible target symbols, the analyzer could create three relationships, each with a confidence of `1/3`. This is a key part of the indexer's "fail-soft" philosophy.

### Example: `instantiates` Relationship (Phase 2)

**Go Code (`test/small-samples/go/main.go`):**
```go
type Car struct { ... }

func main() {
    myCar := Car{}
}
```

Phase 1 extracts the symbol `main.go:Car` and logs an unresolved relationship:
-   `source_qname`: `main.go:main`
-   `target_name`: `Car`
-   `rel_type`: `instantiates`

**Analyzer Logic (`generic_instantiation_analyzer.py`):**
This is a great candidate for a generic analyzer that can be reused across languages.

-   **Location**: `src/code_index_mcp/indexing/relationship_analyzers/common/phase_2/generic_instantiation_analyzer.py`
-   **Logic**:
    1.  Query `unresolved_relationships` for `instantiates`.
    2.  For each one, first look for a symbol named `Car` defined in the same file (`main.go`). A query would look for a symbol with `qname` = `main.go:Car`.
    3.  If not found, look for an `import` relationship from `main.go` that might bring `Car` into scope.
    4.  Once the symbol for `Car` is found, use `writer.add_relationship()` to connect `main.go:main` to `main.go:Car`.
    5.  Delete the unresolved entry.

By breaking down the problem into these phases and small, single-purpose components, adding a new language becomes a methodical process of defining correctness through tests and implementing simple, focused logic to satisfy them.

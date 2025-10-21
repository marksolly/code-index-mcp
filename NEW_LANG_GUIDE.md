# Developer's Guide to Adding a New Language

This guide walks you through adding support for a new language to the code indexer. The architecture is a **phased pipeline** designed to be modular and extensible. You'll add new languages by creating focused "relationship handler" and "extractor" components that plug into this pipeline.

The development process is entirely test-driven. You will first create tests and code samples, then implement the logic to make the tests pass.

## Static Analysis Philosophy

We are creating a probabilistic map of relationships, not a concrete map.

It is bordering on impossible to create a 100% concrete graph of relationships in a codebase without actually executing the code or creating elaborate lookups for every edge case. Therefore, we take a fail-soft approach that is accepting of some ambiguity, while being "good enough" for the mission of uncovering relationships and summarising dependencies.

## The Indexing Pipeline: A Quick Overview

The indexing process happens in three phases:

1.  **Phase 1: Symbol Extraction & Initial Relationship Extraction**: In this phase, a language-specific `SymbolExtractor` parses every file using `tree-sitter`. It identifies all primary symbols (classes, functions, etc.), constructs their qualified names (`qnames`), and records them. It also creates first-order relationships (those that can be determined directly from the file's syntax, like a class containing a method) and extracts unresolved relationships for later phases. Relationship Handlers then extract additional unresolved relationships from the AST for their specific relationship types.

2.  **Phase 2: Intermediate Resolution**: After all symbols are known, relationship handlers run to resolve relationships that can be determined with current knowledge. They look at unresolved relationships and try to solve the straightforward ones, like connecting an `import` statement to the imported file, or a variable's type hint to a class definition in the same file.

3.  **Phase 3: Second Order Resolution**: This final phase handles complex, multi-step resolutions using relationship handlers. For example, to figure out where `my_var.method()` points, a handler first needs to find the type of `my_var` (resolved in Phase 2) and then find `method` on that type.

Each relationship type is handled by a single relationship handler that manages the complete lifecycle of that relationship across all phases. This provides better maintainability, testability, and separation of concerns.

---

## Qualified Names (qnames): The Standard

A core concept is the **qualified name (`qname`)**. It's a context-aware name for a symbol that helps resolve ambiguity. While a simple `name` like `GetUser` could appear in many files, a `qname` provides a more precise identifier, without being globally unique.

Because of the inherent challenge of static analysis, this system is designed to be accepting of some ambiguity.

A qname allows for the formation of probabilistic relationships because it is contextual but not entirely unique.

**The Standard Format:** `<enclosing_scope>(:.)<symbol_name>`

A qualified name must only have two parts. The separator (`:` or `.`) depends on enclosing scope type. Use `.` for object-oriented contexts (class methods) and `:` for file-level contexts (functions in a file).

```
QNAME_VALIDATION_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\[\]]+(:|\.|:__FILE__)[a-zA-Z0-9_\-\[\]]*$")
```

### Examples of Correctly Formed Qnames:

-   **Function in a file**: `my_utils.py:calculate`
-   **Class in a file**: `my_models.py:User`
-   **Method in a class**: `User.get_profile`
-   **File itself**: `my_utils.py:__FILE__` (When the file is the symbol, the file name is the qname with `:__FILE__` suffix).

### Examples of Incorrectly Formed Qnames:

-   `my_models.py:User.get_profile` (Incorrect: Contains three parts. The filename should not be included for class methods.)
-   `Garage.service_car.car` (Incorrect: Contains three parts. Only one enclosing scope should be used.)

**Important**: `qnames` are intended to be reasonably identifying, but not guaranteed to be 100% unique and ambiguity is permitted. They are the primary tool for looking up symbols, but the system's final source of truth is the symbol's integer ID in the database.

### File vs Symbol QName Distinction

To resolve ambiguity between file references and symbol references, file qnames include a `:__FILE__` suffix.

- **File qnames**: `filename.ext:__FILE__` (e.g., `main.go:__FILE__`)
- **Symbol qnames**: Unchanged (e.g., `main.go:MyClass`, `MyClass.method`)

---

## System Architecture Overview

The indexing system is composed of a few key components. Understanding their hierarchy and roles is essential.

```yaml
IndexingOrchestrator:
  description: "The main conductor of the indexing pipeline."
  responsibilities:
    - "Iterates through all files for a given language."
    - "Invokes the correct SymbolExtractor for each file (Phase 1)."
    - "Discovers and runs RelationshipHandlers across all phases."
  interacts_with:
    - LanguageDefinition
    - YourSymbolExtractor
    - YourRelationshipHandler

LanguageDefinition:
  description: "A configuration class that defines the properties of a language."
  responsibilities:
    - "Specifies supported symbol and relationship types."
  used_by:
    - IndexingOrchestrator

YourSymbolExtractor (inherits from BaseSymbolExtractor):
  description: "Parses a single file to find symbols and immediate relationships."
  responsibilities:
    - "Uses tree-sitter to parse the Abstract Syntax Tree (AST)."
    - "Identifies symbols (classes, functions, etc.) and writes them to the database."
    - "Creates immediate relationships and unresolved relationships for later phases."
  phase: 1

YourRelationshipHandler (inherits from BaseRelationshipHandler):
  description: "Manages the complete lifecycle of a specific relationship type."
  responsibilities:
    - "Phase 1: Extracts unresolved relationships from AST."
    - "Phase 2: Resolves relationships using knowledge extracted and saved in Phase 1."
    - "Phase 3: Handles complex multi-step resolution using additional relationships created in Phase 2."
  self_describing:
    - "Declares its relationship_type, required_symbol_types, and phase_dependencies."

BaseRelationshipHandler:
  description: "Abstract base class providing reusable relationship resolution logic."
  inheritance_model:
    - "Each relationship type has a BaseRelationshipHandler in common/ (e.g., BaseImportHandler)."
    - "Language-specific handlers inherit from these base classes (e.g., PythonImportHandler)."
    - "Base classes contain 80-90% of the logic; subclasses implement 3-5 abstract methods."
```
---

## Step 1: Verify the Schema and Define the Language

Before writing any code, you must **verify the database schema** in `src/code_index_mcp/db/database.py`. Ensure that the symbol and relationship types you plan to index are supported. Proposing new relationship types is a significant architectural change and should be avoided if possible.

Once you have confirmed your approach is compatible with the schema, you must define the language's core properties by creating a `LanguageDefinition` class. This class tells the indexer which symbol and relationship types are supported.

-   **Location**: `src/code_index_mcp/indexing/languages.py`
-   **Action**: Create a new class that inherits from `LanguageDefinition` and implement the abstract properties.

### The Power of The Base Relationship Handler Classes

The indexing pipeline uses a an inheritance-based architecture where each relationship type has a base class with reusable logic. Language-specific subclasses only need to implement 3-5 abstract methods to handle their unique AST patterns. Optionally, they can create their own custom implementation instead.

**Your first step should always be to create language-specific subclasses from the base classes.**

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
    def file_extensions(self) -> List[str]:
        return [".go"]

    @property
    def supported_symbol_types(self) -> List[str]:
        return [
            "file",
            "import",
            "class",
            "function",
            "variable",
        ]

    @property
    def supported_relationship_types(self) -> List[str]:
        return [
            "imports",
            "calls",
            "instantiates",
            "is_instance_of",
            "inherits",
        ]
```

### Why is this important?

The base classes provide 80-90% of the relationship resolution logic. You only need to implement language-specific AST parsing methods. This dramatically reduces the amount of code you need to write while ensuring consistency and maintainability.

## Step 2: Create the Test Environment

Before writing any logic, set up the test case for your new language (e.g., "Go").

1.  **Add Code Samples**: Create a directory `test/small-samples/go/`. Add small `.go` files that contain clear examples of the language features you want to index.
2.  **Create a Test Definition**: Create `test/lang_definitions/go.py`. In it, define a `GoTestDefinition` class inheriting from `BaseTestDefinition`.
3.  **Define Expected Relationships**: In your `GoTestDefinition`, create a method `_define_expected_relationships` that returns a list of all relationships you expect to find.
4.  **Define Relationship Dependencies**: Your `GoTestDefinition` must have a `relationship_dependencies` property that defines which relationship types must be resolved before others. The system automatically sorts tests based on these dependencies to ensure they run in the correct logical order.

5.  **Enable Relationships Incrementally**: The `relationship_dependencies` property is the primary mechanism for controlling which relationship types are tested. The `supported_relationships` list is automatically generated from your `relationship_dependencies` keys, and the test runner will *only* run tests for the relationship types defined in `relationship_dependencies`. To follow a Test-Driven Development (TDD) approach:
    a. Define all expected relationships in `_define_expected_relationships`.
    b. Define dependencies in `relationship_dependencies`.
    c. Comment out relationship types in `relationship_dependencies` to test incrementally.
    d. Implement the logic for relationships in dependency order.
    e. Uncomment the next relationship type and repeat.

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
    def relationship_dependencies(self) -> Dict[str, List[str]]:
        """
        Define the dependency order for Go relationships.
        Based on the 3-phase indexing pipeline.
        """
        return {
            # Declaration relationships (Phase 1) - no dependencies
            'declares_file_function': [],
            'declares_class': [],

            # Phase 2: Intermediate resolution - depends on symbol declarations
            'imports': [],
            'instantiates': ['declares_class'],
            'is_instance_of': ['declares_class', 'instantiates'],

            # Phase 3: Final resolution - depends on Phase 2 relationships
            'calls': ['imports', 'declares_class'],
        }

    def get_sample_files(self) -> List[str]:
        return ["test/small-samples/go/main.go"]

    def _define_expected_relationships(self) -> List[Dict[str, Any]]:
        """
        Define the ground truth for relationships in the sample Go files.
        Note: Relationships will be automatically sorted by dependency order.
        """
        return [
            # Test case for the first-order relationship in main.go
            {
                'source_qname': 'main.go:User',
                'type': 'declares_class_method',
                'target_qname': 'User.GetProfile',
                'count': 1
            },
            # Test case for the instantiation in main.go
            {
                'source_qname': 'main.go:main',
                'type': 'instantiates',
                'target_qname': 'main.go:Car',
                'count': 1
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

---

## Step 3: Implement the Symbol Extractor (Phase 1)

The `SymbolExtractor` is the first piece of logic you'll write. Your extractor must inherit from `BaseSymbolExtractor` located in `src/code_index_mcp/indexing/symbol_extractors/base.py`.

### Leveraging the Base Class

The `BaseSymbolExtractor` provides a set of language-agnostic utilities for common tasks, such as traversing the AST and resolving scopes. You should rely on these helpers to reduce boilerplate and ensure consistency. The base class includes methods like:
-   `_get_enclosing_scope_qname`
-   `_get_source_qname_for_node`

It also defines a clear contract through abstract methods that your implementation must provide.

### Core Responsibilities

Your extractor has two main jobs:
1.  Identify all symbols in a file by implementing the abstract methods defined in the base class.
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
    -   After adding both symbols, you would immediately call `writer.add_unresolved_relationship()` to create the `declares_class_method` link between `main.go:User` and `main.go:User.GetProfile`. Although it's resolvable, it's added this way for consistency in the pipeline.

4.  **Handling `instantiates` and `is_instance_of`**:
    -   When an assignment involves a class instantiation (e.g., `my_var = MyClass()`), the extractor should create **two** unresolved relationships:
        1.  An `instantiates` relationship from the enclosing function/method to the class (`MyClass`).
        2.  An `is_instance_of` relationship from the variable (`my_var`) to the class (`MyClass`).
    -   This ensures that the indexer captures both the instantiation event and the type of the resulting variable.

5.  **Create an Unresolved Relationship**: If `GetProfile` called another function, `GetPermissions()`, that would be an unresolved `calls` relationship, because the extractor doesn't know where `GetPermissions` is defined without a wider project view. You would log this in the `unresolved_relationships` table for the analyzers in Phase 2/3 to solve.

6.  **Handling Complex Lookups with `intermediate_symbol_qname`**:
    -   For complex call chains like `my_var.engine.start()`, the extractor cannot directly resolve `start()`. It first needs to know the type of `my_var.engine`.
    -   To handle this, the `add_unresolved_relationship` method accepts an `intermediate_symbol_qname` parameter. The extractor should provide the qname of the intermediate symbol (`my_var.engine` in this case).
    -   The handler can then use this information in Phase 3 to perform a two-step lookup: first, find the type of `my_var.engine` (which must have been resolved in Phase 2), and then find the `start` method on that type.

---

## Step 4: Implement Relationship Handlers (Phase 1, 2 & 3)

After you have a working `SymbolExtractor`, you can start implementing `RelationshipHandler` classes. These are responsible for managing the complete lifecycle of specific relationship types across all phases.

### Leveraging Base Classes and Inheritance

Before writing a new handler, check the `src/code_index_mcp/indexing/relationship_handlers/common/` directory. This directory contains **abstract base classes** (not concrete handlers) that provide reusable logic for common relationship types.

**You should strive to inherit from a base class rather than writing a handler from scratch.** The base classes contain most of the relationship resolution logic, so you only need to implement 3-5 abstract methods for language-specific AST parsing.

-   **Location**: `src/code_index_mcp/indexing/relationship_handlers/{language}/`
-   **Naming**: `{Language}{RelationshipType}Handler` (e.g., `GoImportHandler`, `JavaScriptCallHandler`)
-   **Principle**: One class, one relationship type per language
-   **Self-Describing**: Handlers declare their `relationship_type`, `required_symbol_types`, and `phase_dependencies`
-   **Unified Lifecycle**: Each handler manages extraction (Phase 1), immediate resolution (Phase 2), and complex resolution (Phase 3)

### Available Base Classes

The `common/` directory contains these abstract base classes:

- `BaseImportHandler` - For import relationship resolution
- `BaseInheritsHandler` - For inheritance relationship resolution
- `BaseInstantiationHandler` - For class instantiation resolution
- `BaseFileFunctionCallHandler` - For file-level function call resolution
- `BaseMemberFunctionCallHandler` - For method/member call resolution
- `BaseIsInstanceOfHandler` - For type/instance relationship resolution

### A Note on Pragmatism and Creative Solutions

The goal of the indexer is to provide a "good enough" overview of a codebase, not to create a perfect, 100% complete representation. This is especially true for complex features like variable scoping.

-   **Focus on High-Signal Symbols**: When implementing features like variable tracking, prioritize "high-signal" symbols (e.g., module-level exports, constants) over indexing every local variable. This reduces noise and complexity.
-   **Work Within Constraints**: Before proposing new relationship types, consider if you can creatively repurpose existing, supported types to achieve your goal. For example, using an `is_instance_of` relationship to represent a class alias is a pragmatic way to solve a language-specific problem without requiring schema changes. This embraces the "fail-soft" philosophy of the indexer.

### The Inheritance Mechanism and Confidence Scoring

The orchestrator automatically discovers language-specific handlers from the `{language}/` directories. For each relationship type in your language definition:

1. The orchestrator looks for `{Language}{RelationshipType}Handler` in the `{language}/` directory
2. If found, it instantiates and uses your language-specific implementation
3. If not found, the relationship type is skipped for your language

**Custom Implementations**: If a base class doesn't meet your needs, you can create a completely custom handler by inheriting directly from `BaseRelationshipHandler`. However, this should be rare since the base classes are designed to be highly reusable.

**Confidence Scoring**: The `IndexWriter.add_relationship` method supports a `confidence` parameter (a float between 0.0 and 1.0). This is useful for handling ambiguity. If a handler cannot uniquely identify a target symbol, it can create multiple low-confidence relationships. For example, if there are three possible target symbols, the handler could create three relationships, each with a confidence of `1/3`. This is a key part of the indexer's "fail-soft" philosophy.

confidence = 1 / num_candidates

## Debugging

-   **To run the entire suite for all languages:**
    ```bash
    uv run python test/test_language_support_suite.py --failfast
    ```

-   **To run tests for only your new language (e.g., Go):**
    ```bash
    uv run python test/test_language_support_suite.py --language=go --failfast
    ```

The `--failfast` flag will stop the test run on the first failure, which is useful for focused, iterative development. In addition, when `--failfast` specified, the suite runner provides a detailed log to help you diagnose the issue. Here’s a step-by-step guide to debugging common problems:

1.  **Analyze the Failure**: The traceback will point to the exact assertion that failed. The error message will tell you what relationship was expected and what was actually found (or not found).

2.  **Inspect the Relationship Dump**: The test output includes a (filtered) dump of all incoming and outgoing relationships for the source and target symbols involved in the failed test. This is your primary tool for understanding what the indexer *thinks* is happening.

3.  **Common Issues**:
    *   **Incorrect Relationships**: If a relationship is missing or incorrect, trace back the logic in your `SymbolExtractor` or `RelationshipHandler`. Are you creating the unresolved relationship correctly? Is your handler finding the correct target symbol?
    *   **Ambiguous Symbols**: If multiple symbols have the same name, does your handler capture the correct one. Or, have you failed to embrace ambiguity and need to create several lower confidence relationships?
    *   **Qname Mismatches**: Ensure the `qname`s you are creating in your extractor matches the format expected by your test definitions.

4.  **Direct Database Inspection**: For complex issues, you can inspect the `test_code_index.db` file directly using `sqlite` on the command line or `sqlitebrowser` (GUI). This allows you to see the raw data and get a clear picture of what symbols and relationships were created.

This SQL query joins the relationships, code_symbols, and relationship_types tables to show all relationships in a human-readable format, displaying source symbol names/qnames, relationship types, and target symbol names/qnames. The results are ordered by source qname for easier analysis:

```sql
sqlite3 test_code_index.db "SELECT s1.name as source_name, s1.qname as source_qname, rt.name as rel_type, s2.name as target_name, s2.qname as target_qname FROM relationships r JOIN code_symbols s1 ON r.source_symbol_id = s1.id JOIN code_symbols s2 ON r.target_symbol_id = s2.id JOIN relationship_types rt ON r.type_id = rt.id ORDER BY source_qname;"
```

Checking for duplicate relationships (always include the language):
```sql
sqlite3 test_code_index.db "SELECT f.language, COUNT(*) as count, s1.name as source_name, s1.qname as source_qname, rt.name as rel_type, s2.name as target_name, s2.qname as target_qname FROM relationships r JOIN code_symbols s1 ON r.source_symbol_id = s1.id JOIN code_symbols s2 ON r.target_symbol_id = s2.id JOIN relationship_types rt ON r.type_id = rt.id JOIN files f ON s1.file_id = f.id GROUP BY source_qname, rel_type, target_qname, f.language HAVING COUNT(*) >= 2 ORDER BY source_qname;"
```

Checking for unresolved relationships:
```sql
SELECT  f.language, s1.qname as source_qname, rt.name as rel_type, r.intermediate_symbol_qname, r.target_name, r.target_qname, r.creator_location, r.target_resolver_name
FROM unresolved_relationships r 
JOIN code_symbols s1 ON r.source_symbol_id = s1.id 
JOIN relationship_types rt ON r.relationship_type_id = rt.id 
JOIN files f ON s1.file_id = f.id
ORDER BY language, source_qname;
```

6.  **Logging**: If you need more detailed information, you can add more logging to your extractors and analyzers. The `--failfast` flag will re-run the indexer with more verbose logging for the failed test case.

## Step 5: Debugging Cross-Language Issues and Unresolved Relationships

**Always Include Language in Debugging Queries**

When debugging unresolved relationships (especially in STRICT MODE violations), **always include language information in your SQL queries**. This single mistake can waste significant time.

**Bad Query (will show cross-language confusion):**
```sql
SELECT s1.qname as source_qname, ur.target_name, ur.intermediate_symbol_qname
FROM unresolved_relationships ur
JOIN code_symbols s1 ON ur.source_symbol_id = s1.id
ORDER BY source_qname;
```

**Good Query (includes language for clarity):**
```sql
SELECT f.language, s1.qname as source_qname, ur.target_name, ur.intermediate_symbol_qname
FROM unresolved_relationships ur
JOIN code_symbols s1 ON ur.source_symbol_id = s1.id
JOIN files f ON s1.file_id = f.id
ORDER BY f.language, source_qname;
```
### Common Cross-Language Issues

The test suite processes files from all supported languages (Python, JavaScript, PHP) in a single run, which can create unexpected cross-language conflicts.

**Pattern 1: Language-Specific Built-in Method Calls**
- **JavaScript**: `arr.push()`, `console.log()` - these create unresolved relationships because they're built-in
- **Python**: `list.append()`, `dict.keys()` - same issue with built-in methods
- **PHP**: Similar built-in method issues

### Language-Specific Handler Extensions

Add `resolve_complex` methods to handle built-in methods that can't be resolved through source code relationships:

```python
# Example: PythonMemberFunctionCallHandler
def resolve_complex(self, writer, reader):
    super().resolve_complex(writer, reader)
    
    unresolved = reader.find_unresolved("calls_class_method", language=self.language)
    
    for rel in unresolved:
        if self._is_builtin_method(rel['target_name']):
            # Delete - these are resolved as "built-in, no relationship needed"
            writer.delete_unresolved_relationship(rel['id'])
```
**Cross-Language Debugging Checklist**
- [ ] Include language columns in all SQL queries
- [ ] Check for built-in method calls across supported languages
- [ ] Verify unresolved relationships aren't from different language files
- [ ] Add appropriate `resolve_complex` methods for each language
- [ ] Test individual language handlers before full multi-language suite

## Notes for LLMs, Agents and Coding Assistants
Attention: Claude, Cline, Cursor, Grok, Gemini & others.

Working with this codebase requires having "the big picture" and using all the component classes together correctly. To operate effectively you also need a well defined plan because implementing a new language will exceed context length and contains too many details to execute in a single session.

### Executing Python Scripts

This project uses a virtual environment which can be activated with:
`source /<...full path...>/code-scope-mcp/.venv/bin/activate`

This project uses `uv`. Any scripts you run must be invoked with `uv run`.

### Discovery
In the first instance, use code-scope-mcp `find_symbols` tool for discovery (if available). When applicable files have been identified, agents and assistants are recommended to perform a bulk read before planning or beginning any task. Eg:
`rg --files <file_or_folder1> <file_or_folder2> [<file_or_folder3>...]  | xargs -I {} sh -c 'echo "--- {} ---"; cat {}; echo'`

### Off Limits - Read Only Files
LLMs, agents and coding assistants are forbidden to modify the following files.

Read Only: 
   - orchestrator.py (IndexingOrchestrator)
   - reader.py (IndexReader)
   - writer.py (IndexWriter)

If you think you need to modify these files, reassess your plan carefully and gather more context, you have missed something.

### Test & Debugging

#### Good Debug Commands

Examples of high quality, effective test & debugging commands:

 > uv run python test/test_language_support_suite.py --help
 > uv run python test/test_language_support_suite.py
 > uv run python test/test_language_support_suite.py --language=c --debug-components="BaseImportHandler,CFunctionExtractor,CImportHandler" --failfast
 > sqlite "SELECT FROM ... JOIN ... WHERE;"
 > uv run python cli.py query --help
 > uv run python cli.py query --db-path='test_code_index.db' ...

#### Bad Debugging Commands

Banned. Not allowed. Off limits. Undesirable. Awful. Terrible.
Prohibido, No permitido, Acceso restringido, Indeseable.
Interdit, Non autorisé, Accès interdit, Indésirable.
Verboten, Nicht erlaubt, Zutritt verboten, Unerwünscht, Schrecklich, Furchtbar.
被禁止的, 不允许, 禁止入内, 不受欢迎的, 糟糕的, 可怕的

 > python -c "..."
 > python test/test_language_support_suite.py
 > uv run python test/test_language_support_suite.py | tail -20
 > uv run python test/test_language_support_suite.py | grep ...
 > uv run python test/test_language_support_suite.py | head -10

### Planning
Before working on a new language, LLMs & agents should insist on creating a detailed implementation plan containing a checklist with checkboxes. They should keep that checklist updated with their progress.

A plan must include these sections:
    1. List of symbols to be extracted (minimum is: `file`).
    2. Section on relationships to be supported.
        For each relationship:
        2.1.  Processing required in Phase 1 (eg: extraction from AST, create unresolved relationships).
        2.2.  Processing required in Phase 2 (eg: immediate resolution using saved symbols and relationships from Phase 1).
        2.3.  Processing required in Phase 3 (eg: Second order resolutions using relationships created in Phase 2).
    3. Relationship Dependencies
        Define which relationship types must be resolved before others using the `relationship_dependencies` property.
        The test suite automatically sorts tests based on these dependencies to ensure correct execution order. This will also help guide your phase 2 and phase 3 design.
        Example: `'calls': ['imports', 'declares_class']`
    4. List of Base Classes to inherit from and rationale for using each.
        Check `src/code_index_mcp/indexing/relationship_handlers/common/` for available base classes.
        Example: `BaseImportHandler` for handling import relationships (provides 80-90% of logic).
    5. List of Base Classes that may not be suitable.
        Make sure you say why a base class is not suitable. Identifying the deficiency will help determine if you need a custom implementation.
        Example: `BaseImportHandler` doesn't handle language-specific import syntax patterns.
    6. List of proposed new Handler classes.
        Specify which relationship types need custom handlers and why.
        Example: `GoImportHandler` inheriting from `BaseImportHandler` for Go-specific import patterns.
    7. List of relevant files for context, including which files from other languages will be used as examples.
        Example: Look at `python_symbol_extractor.py` for symbol extraction patterns.
    8. List of unknowns and assumptions.
        Example: Assuming tree-sitter grammar for the language is available.
    9. A detailed implementation checklist with checkboxes based on this guide.
        Include specific tasks like:
        - [ ] Create language definition in `languages.py`
        - [ ] Implement symbol extractor
        - [ ] Create language-specific handlers inheriting from base classes
        - [ ] Update tests
        - [ ] Validate with test suite (iteratively)

### Critical REMINDER
Use `uv run`. Do not attempt to run python directly.

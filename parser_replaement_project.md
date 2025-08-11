# Multi-Language Code Graph Extraction Enhancement Plan

## Executive Summary

This document outlines a plan to enhance the Code Index MCP project with multi-language graph extraction for the top 10 languages (JavaScript, Python, TypeScript, PHP, C++, C#, Go, Ruby, Swift, Java, Rust). The graph will include symbols (functions, classes, constants, globals, variables, files) and relationships (calls, inheritance, imports, instantiations, overrides, variable references). Tree-sitter will be used for parsing, with static analysis, qnames for uniqueness, and numeric confidence scoring for ambiguities. The system will support incremental indexing, handle 100k+ LOC codebases with 1-2 second queries, and run on Linux (mandatory), Windows/macOS (desired), all architectures.

## Requirements

### Functional Requirements

- **Multi-Language Support**: Parse and index code from the top 10 languages: JavaScript, Python, TypeScript, PHP, C++, C#, Go, Ruby, Swift, Java, Rust. Use existing open-source parsers (e.g., Tree-sitter) to extract symbols and relationships without custom parser development unless absolutely necessary.
- **Symbol Extraction**: Capture core symbols including:
  - Functions/methods (names, parameters).
  - Classes (definitions, methods).
  - Namespaces.
  - Constants and globals.
  - Imports/exports/includes/requires.
  - Variables (usages/references beyond immediate scope).
  - Files (treated as searchable symbols).
- **Relationship Extraction**: Build a graph capturing:
  - Function/method calls (inter-file, inter-class).
  - Inheritance hierarchies (parent-child).
  - Import/dependency chains.
  - Namespace definitions and memberships.
  - Instantiations/constructor calls.
  - Overrides/implementations (e.g., interface methods).
  - Variable references beyond immediate scope.
  - Suggestions for additional symbols/relationships (e.g., exports as a symbol type) can be incorporated if they enhance structure understanding without complexity.
- **Ambiguous Relationship Handling**: For ambiguous targets (e.g., multiple matching symbols), create multiple relationships with numeric confidence score (1 / number of matches). Use qualified names (qnames) for better uniqueness:
  - Primary: Enclosing scope (e.g., `User.save` for method `save` in class `User`).
  - Fallback: File name (e.g., `audit.py:log_event`).
- **Incremental Indexing**: Support updates via file watchers for create/update/delete, re-indexing only affected files.
- **Static Analysis Only**: No dynamic analysis; attempt import resolution with low-confidence matches for ambiguities.
- **Edge Case Handling**: Gracefully handle minified/obfuscated code (e.g., skip or fail softly via .indexerignore or error logging).
- **Query Example**: Extend tools like `find_symbols` to return graph edges/nodes for matched symbols (as in the provided project plan example).

### Non-Functional Requirements

- **Performance**: Handle 100k LOC codebases minimally; query response in 1-2 seconds; memory usage up to 1GB acceptable but should coexist with other apps on 16GB+ RAM systems.
- **Scalability**: Support large codebases (e.g., 10 repos, websites, API servers, mobile apps, firmware) with multi-language mixes.
- **Platforms**: Mandatory Linux support (Mint, Ubuntu); desired Windows and macOS. All CPU architectures (e.g., x86, ARM).
- **Installation/Setup**: Simple for non-experts; use existing methods like `uvx code-index-mcp` or git clone + `uv sync`. Dynamic download of parser grammars (e.g., via pip/script) is acceptable.
- **Licensing**: All dependencies must be MIT-compatible; no changes to project's MIT license.
- **Extensibility**: Parser integration should allow easy addition of new languages.
- **Encoding/Files**: Assume UTF-8; skip binaries/hidden files as per existing.
- **Incomplete Parsers**: Best-effort support; prioritize languages by listed order if parsers are limited.

## High-Level Plan

The enhancement will proceed in four phases:

1. **Phase 1: Parser Selection and Setup**: Integrate Tree-sitter for multi-language parsing. Delete legacy analyzers and design a new extensible analyzer system.

2. **Phase 2: Schema Extensions and Core Indexing Updates**: Minimally extend the SQLite schema for new symbols/relationships. Update the IndexBuilder and RelationshipTracker (clean slate) to extract and store the required graph data.

3. **Phase 3: Language-Specific Implementation**: Implement parsers and relationship extractors for each of the top 10 languages, starting with highest priority (JavaScript first).

4. **Phase 4: Integration and Optimization**: Integrate with existing services (e.g., file watchers for incremental updates), optimize for performance, and extend tools like `find_symbols` for graph queries.

## Relevant Files for Context

Key files from the project codebase (based on provided combined_code.txt) that developers should reference:

- `./src/code_index_mcp/analyzers/__init__.py`: Defines the `LanguageAnalyzerManager` and `TreeSitterAnalyzer`.
- `./src/code_index_mcp/indexing/__init__.py`: Defines models (e.g., FileInfo, FunctionInfo, ClassInfo, ImportInfo, CodeIndex) and exports core classes like IndexBuilder, ProjectScanner.
- `./src/code_index_mcp/indexing/scanner.py`: Handles project scanning, file discovery, categorization, and ignore logic (e.g., .indexerignore, supported extensions).
- `./src/code_index_mcp/indexing/builder.py`: Coordinates indexing, analysis, and relationship building; integrate new parsers here.
- `./src/code_index_mcp/services/database.py`: Manages SQLite connection and schema; extend DDL here if needed.
- `./src/code_index_mcp/services/index_service.py`: Manages index building, updates, and file operations; update for incremental graph extraction.
- `./src/code_index_mcp/services/file_watcher_service.py`: Handles file change detection for incremental indexing.
- `./src/code_index_mcp/server.py`: Defines MCP tools; extend for graph queries if needed.
- `./src/code_index_mcp/constants.py`: Lists supported extensions; update for new languages if necessary.

These files form the core of indexing and storage. Refer to them for integration points; delete or refactor legacy parsing code as planned.

## Parser Selection and Integration

Tree-sitter is selected as the primary parser due to its support for all top 10 languages, static analysis capabilities, MIT license, and lightweight Python bindings. It uses language-specific grammars (small binaries) downloadable dynamically via pip (e.g., `tree-sitter-languages` package).

### License Implications for Tree-Sitter

- Tree-sitter core library and Python bindings (`tree-sitter` PyPI package) are licensed under MIT.
- Individual language grammars (e.g., tree-sitter-javascript) are also MIT-licensed.
- Integration is fully compatible with the project's MIT license; no copyleft issues or forced license changes.
- Dependencies: Requires `tree-sitter` package (install via pip); grammars can be bundled or downloaded on first use.
- Risks: If a grammar is incomplete (e.g., for niche features), fall back to best-effort parsing without errors.

Integration Approach:
- Create a generic `TreeSitterAnalyzer` in `indexing/analyzers.py` that loads grammars per language.
- Subclass or configure for language-specific quirks (e.g., C++ macros).
- Make extensible: Add new languages by registering grammar names and extraction logic.

## Qualified Name (`qname`) Definition

To improve uniqueness and provide better context, each symbol will have a `qname`. The `qname` is the symbol's qualified name relative to its context, determined by the AST. It is constructed by traversing the AST upwards from the symbol's node and concatenating the names of enclosing scopes (namespaces, classes).

*   **Primary Rule (Enclosing Scope)**: If a symbol is within one or more enclosing scopes (like a class or namespace), the names of these scopes are prepended to the symbol's name to form the `qname`.
    *   *Example (Class Scope)*: A `save` method in a `User` class has the `qname` `User.save`.
    *   *Example (Namespace Scope)*: A `Helper` class inside a `Utils` namespace has the `qname` `Utils\Helper`.
    *   *Example (Nested Namespace)*: A function `log` in namespace `Internal` which is inside namespace `Logging` would have the `qname` `Logging\Internal\log`.
*   **Fallback Rule (File Name)**: If a symbol has no other enclosing scope (e.g., a top-level function), the file's name is used as the qualifier.
    *   *Example*: A function `log_event` in `audit.py` has the `qname` `audit.py:log_event`.

## Ambiguous Relationship Handling

When a function call's target is ambiguous (i.e., its name matches multiple symbols in the codebase), this system will not guess. Instead, it will:
1.  Create multiple, distinct relationships—one for each potential target.
2.  Mark each of these relationships with a "low confidence" score.
3.  The user interface will then visually distinguish these low-confidence links (e.g., with a `?`) and can show the user all potential targets.

### Confidence Scoring
- **Numeric Model**: Score = 1 / number_of_matches (e.g., unique match = 1.0; 2 matches = 0.5; 3 = ~0.33).
  - Store in `relationships.confidence` column (REAL, default 1.0).
  - For low scores, mark in queries (e.g., with '?' in `find_symbols` output if <0.5).
- **Storage and Query**: In tools like `find_symbols`, filter or annotate based on score (e.g., show only >0.5 or label low ones).

## Unknowns, Risks & Assumptions

- **Unknowns**: Exact performance on very large codebases (e.g., 10+ repos); completeness of Tree-sitter grammars for edge cases like C++ macros or Python decorators; impact of ambiguity on graph noise.
- **Risks**:
  - Incomplete parsers: Some languages (e.g., Rust overrides) may have partial support; mitigate with best-effort indexing and logging.
  - Ambiguous resolutions: Low-confidence matches could lead to noisy graphs; mitigate by marking them clearly in queries and using heuristics.
  - Performance degradation on large graphs: Queries might exceed 2s; mitigate with indexes and limits.
  - Platform compatibility: Tree-sitter binaries may need per-arch builds; assume pip handles this.
  - Minified code: Could cause parse failures; mitigate by skipping via .indexerignore or soft errors.
- **Assumptions**:
  - Tree-sitter suffices for static analysis needs; no need for heavier tools like libclang.
  - Users have internet for initial setup (grammar downloads).
  - Codebases are UTF-8; binaries/hidden files skipped as per existing.
  - Large codebases are multi-language but not excessively obfuscated.

## SQL DDL Statements

The existing schema (from `database.py`) is retained with minimal extensions for new relationship types (e.g., 'references_variable', 'overrides', 'exports_to'). Add a `confidence` column to `relationships` for scoring. Execute in `DatabaseService.initialize_db`:

```sql
-- Add confidence column to relationships (if not exists)
ALTER TABLE relationships ADD COLUMN confidence REAL DEFAULT 1.0;

-- Add new symbol types if needed (e.g., for globals/variables)
INSERT OR IGNORE INTO symbol_types (name) VALUES ('global'), ('variable'), ('export');

-- Add new relationship types
INSERT OR IGNORE INTO relationship_types (name) VALUES ('references_variable'), ('overrides'), ('exports_to'), ('instantiates');
```

These extensions support the required relationships and scoring without altering structure.

## Detailed Implementation Checklist

### Phase 1: Parser Selection and Setup

- [x] Install Tree-sitter dependencies: Add `tree-sitter` and `tree-sitter-languages` to project requirements (e.g., pyproject.toml).
- [x] Delete legacy analyzers: Remove any existing language-specific classes in `indexing/analyzers.py` or submodules.
- [x] Create `TreeSitterAnalyzer` class in `indexing/analyzers.py`: Implement generic parsing logic to load grammars, parse AST, and extract symbols (functions, classes, etc.).
- [x] Update `LanguageAnalyzerManager` in `indexing/__init__.py`: Register Tree-sitter for all top 10 languages; map extensions to grammars (e.g., '.js' -> 'javascript').
- [x] Handle dynamic grammar downloads: In analyzer init, check and download missing grammars via Tree-sitter API.

### Phase 2: Schema Extensions and Core Indexing Updates

- [x] Extend schema in `services/database.py`: Add the proposed ALTER and INSERTs for confidence column and new types in `initialize_db`.
- [x] Delete existing RelationshipTracker: Remove `relationships.py` or equivalent; implement clean-slate in `indexing/builder.py` as `GraphBuilder` class.
- [x] Update `IndexBuilder.build_index` in `indexing/builder.py`: Integrate new analyzer, extract symbols/relationships.
- [x] Implement namespace-aware qname generation: Update `_extract_qname` to traverse the full AST path, including namespaces, to construct a fully qualified name.
- [x] Add ambiguous handling: For matches with multiple targets, insert multiple relationships with confidence score (1 / number_of_matches) in the new column; use heuristics like scope proximity to refine if possible.
- [ ] Implement qname generation: In symbol extraction, apply primary (enclosing scope) and fallback (file-based) rules. 
- [x] **New** Refactor `ClassInfo` model: Update the `ClassInfo` data model to store a list of full `FunctionInfo` objects instead of just method names. See `feature_update_class_info_model.md` for the detailed plan.

### Phase 3a: Language-Specific Implementation

- [x] JavaScript: Implemented language-specific queries and improved symbol extraction logic in `TreeSitterAnalyzer`.
- [x] Python: Implemented language-specific queries and adapted symbol extraction logic.
- [x] TypeScript: Implement language config and extraction logic.
- [x] PHP: Implement language config and extraction logic.
- [x] C++: Implement language config and extraction logic (ensure namespace support).
- [x] C#: Implement language config and extraction logic.

### Phase 3b: Verify Functionality

- [ ] Implement integration test suite: Create a small set of tests for the initial language (JavaScript) to verify end-to-end graph extraction. See the `test` directory for existing test data. Prioritise designing a test that can be run with a single command but returns more insight than just a single pass/fail result (fail soft). (task is 30% complete)
  - [x] Make existing basic test run. Need to resolve Python "import hell" (sorry!).
  - [x] Expand tests to actually verify parser functionality.

### Phase 3c: Additional Language-Specific Implementation

- [ ] Go: Implement language config and extraction logic.
- [ ] Ruby: Implement language config and extraction logic.
- [ ] Swift: Implement language config and extraction logic.
- [ ] Java: Implement language config and extraction logic.
- [ ] Rust: Implement language config and extraction logic.
- [ ] Best-effort fallback: If parser fails (e.g., incomplete grammar), log error and skip file gracefully.

### Phase 3d: Non-Procedural Language Support (HTML & CSS)

- [ ] HTML: Implement language config and extraction logic.
  - **Symbol Extraction**: `id`, `class`, `link` (href), `src` attributes.
  - **Relationship Extraction**: `uses_class`.
- [ ] CSS: Implement language config and extraction logic.
  - **Symbol Extraction**: `selector`, `variable`.
  - **Relationship Extraction**: `targets_selector`, `imports`, `references_url`, `uses_variable`.

### Phase 4: Integration and Optimization

- [ ] Integrate with `index_service.py`: Update `_index_project`, `update_file`, `remove_file` to use new graph builder; ensure incremental updates cascade to relationships and recompute confidences.
- [ ] Update file watcher in `file_watcher_service.py`: Trigger graph re-extraction on changes.
- [ ] Optimize database: Add indexes on confidence if needed; test queries for 1-2s response with ambiguous filtering.
- [ ] Extend `find_symbols` in `server.py` and `search_service.py`: Support returning graph edges (e.g., matched symbols + adjacent nodes/edges) with confidence annotations (e.g., '?' for <0.5).
- [ ] Implement compatibility layer for `get_file_summary`: Create a function to query the new graph database and reconstruct file summary data in the legacy format expected by `FileService.analyze_file`. This ensures backward compatibility for the `get_file_summary` tool.
- [ ] Extend test suite to verify functionality for explicitly supported languages.
- [ ] Platform testing prep: Ensure setup scripts handle Linux/Windows/macOS; use cross-platform paths in code.
- [ ] Documentation updates: Add to README how to add new languages; note best-effort for incomplete parsers and ambiguity handling.

## Post-Project Installation

Upon completion of this enhancement project, installation for users of the code-index-mcp tool remains unchanged and simple. Users can run the tool directly with `uvx code-index-mcp`, which will automatically handle the new dependencies (e.g., Tree-sitter) via pre-compiled wheels available for all supported platforms. For development or local setup, git clone the repository followed by `uv sync` will install everything, including dynamic grammar downloads on first use. No additional steps or compilers are required, ensuring a lightweight experience.

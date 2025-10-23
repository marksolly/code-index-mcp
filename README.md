# Code Scope MCP

<div align="center">

[![MCP Server](https://img.shields.io/badge/MCP-Server-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

**Code Scope: Graph-Powered Code Explorer for LLMs**

Gives your AI coding tool deep insight into your large codebase without burning huge numbers of tokens.

Designed for codebases spanning 100,000+ lines of code and thousands of files.

</div>

## Table of Contents

- [Overview](#overview)
- [Interfaces](#interfaces)
- [Use Cases](#use-cases)
- [Quick Start](#quick-start)
- [Usage Examples](#usage-examples)
- [Available Tools](#available-tools)
- [Troubleshooting](#troubleshooting)
- [Development & Contributing](#development--contributing)
- [License](#license)

## Overview

Code Scope MCP is a **stdio-based [Model Context Protocol](https://modelcontextprotocol.io) server** that bridges the gap between AI models and complex codebases.

When codebases grow large or when working across multiple repos it can be difficult for AI code assistants to understand the full scope of requests or the full impact of changes they make.

This MCP server maintains an index your code base and makes fast, token efficient, code-graph search and reporting tools available.

## Architecture

**Local STDIO Server**: Runs as a subprocess within MCP-compatible applications
- **Communication**: Uses standard input/output streams (stdio) for MCP protocol
- **Security**: No network exposure - only accessible to the host application
- **Performance**: Direct process communication with minimal overhead
- **Database**: Requires local file system access to SQLite database files

## Interfaces

Code Scope provides two ways to access its powerful code indexing capabilities:

### **MCP Server (Primary Interface)**
- **Type**: Stdio-based local server subprocess
- **For AI Coding Assistants**: Designed to be integrated into AI tools like Claude Code and Cline
- **Contextual Search**: Provides AI assistants with deep code understanding and relationship analysis
- **Token Efficient**: Delivers comprehensive code insights without burning through token limits
- **Real-time Analysis**: Helps AI assistants understand code impact before making changes
- **Security**: No network access required - communicates via stdio with host application

### **CLI Tool (Direct Access)**
- **Standalone Usage**: Command-line interface for direct querying of indexed codebases
- **Same Technology**: Uses the identical indexing engine as the MCP server
- **Debugging & Analysis**: Useful for manual exploration and troubleshooting
- **Development**: Helps developers understand their codebase structure

Both interfaces share the same underlying index.

## CLI Tool Usage

The CLI tool provides direct access to the same indexing and search functionality as the MCP server. It's useful for development, debugging, and manual exploration.

### **Installation & Setup**

```bash
# Clone the repository
git clone https://github.com/marksolly/code-scope-mcp.git
cd code-scope-mcp

# Install dependencies
uv sync

# Use the CLI
uv run python cli.py --help
```

### **CLI Commands**

#### **Index Command**
Create a new code index database from a directory:

```bash
# Basic indexing
uv run python cli.py index /path/to/your/project

# Custom database location
uv run python cli.py index /path/to/project --db-path my_project.db

# With profiling (shows performance metrics)
uv run python cli.py index /path/to/project --profile
```

#### **Update Command**
Incrementally update an existing index:

```bash
# Update specific files
uv run python cli.py update src/main.py src/utils.py --db-path my_project.db

# Update entire directories
uv run python cli.py update src/ tests/ --db-path my_project.db
```

#### **Query Command**
Search the indexed codebase:

```bash
# Basic search - all symbols
uv run python cli.py query "*"

# Search for classes
uv run python cli.py query "*" --symbol-type class

# Search with pattern
uv run python cli.py query "User*" --symbol-type class

# Multiple symbol types
uv run python cli.py query "*" --symbol-type class --symbol-type function

# Filter by file path
uv run python cli.py query "*" --path-pattern "src/**/*.py"

# Filter by language
uv run python cli.py query "*" --language python

# Include context information
uv run python cli.py query "getUser" --include-context relationships --include-context properties

# Case-sensitive search
uv run python cli.py query "User" --case-sensitive

# Limit results
uv run python cli.py query "*" --limit 10

# Regex mode (instead of glob)
uv run python cli.py query "get.*User" --match-mode regex
```

### **CLI Examples**

```bash
# Find all classes in the project
uv run python cli.py query "*" --symbol-type class --limit 20

# Find functions related to user management
uv run python cli.py query "*user*" --symbol-type function --case-sensitive false

# Find all methods in a specific file
uv run python cli.py query "*" --symbol-type method --path-pattern "**/user_service.py"

# Complex query with multiple filters
uv run python cli.py query "get*" --symbol-type function --symbol-type method --include-context relationships
```

### **CLI vs MCP Server**

| Feature | CLI Tool | MCP Server |
|---------|----------|------------|
| **Usage** | Direct command-line access | Integrated into AI tools |
| **Output** | Terminal text | Structured tool responses |
| **Database** | Specified via `--db-path` | Specified per tool call |
| **Best for** | Development, debugging, manual queries | AI assistant integration |
| **Installation** | Local development setup | Package installation |

## Use Cases

Helps your AI tools answer these questions:

- Where is the thing the user is asking about?
- How does this thing relate to the codebase?
- What are the consequences of changing this thing?

### Discovery

When a user asks an abstract question about a codebase, the tools provided by this MCP server allow AI agents to rapidly find relevant code without resorting to slow full text searches. Reduces the need to include a large number of files with the users initial request.

### Finding Relationships

Helps AI coding tools quickly identify how the component they are working on relates to the rest of the code base.

**Example**

When modifying a method name in a class, a single query to `find_symbols` will return a compact graph showing what other parts of the codebase call that method inside that class.

**Sample Response**

```text
[function] get_user(user_id: int)
  -> calls: db.query, logger.info
  <- called_by: get_user_profile, update_user_settings
  |> in: src/services/user_service.py

[file] src/services/user_service.py
  - contains: get_user, update_user, delete_user
  <- imported_by: src/api/v1/users.py

[class] User
  - inherits: BaseModel
  - contains: to_dict(), from_dict(data)
  -> instantiated_in: create_user, get_user_profile
  |> in: src/models/user.py

[import] fastapi
  <- imported_by: src/server.py, src/api/v1/users.py
  |> in: fastapi

[constant] MAX_RETRIES
  -> used_in: retry_operation
  |> in: src/config.py
```

## **Multi-Language Support**

Code Scope MCP supports:

- Python
- JavaScript
- TypeScript
- Java
- C++
- C#
- Go
- Ruby
- PHP
- Swift
- Rust
- HTML
- CSS

**Symbol Extraction**: Capture core symbols including:

- Functions/methods (names, parameters).
- Classes (definitions, methods).
- Namespaces.
- Constants and globals.
- Imports/exports/includes/requires.
- Files (treated as searchable symbols).
- **Relationship Extraction**: Build a graph capturing:

  - Function/method calls (inter-file, inter-class).
  - Inheritance hierarchies (parent-child).
  - Import/dependency chains.
  - Namespace definitions and memberships.
  - Instantiations/constructor calls.
  - Overrides/implementations (e.g., interface methods).

## Quick Start

### **MCP Server Installation**

The SymbolFinder is now available as a working MCP server! Install it directly into your MCP-compatible tools.

**Prerequisites:** 

* Python 3.10+ 
* [uv](https://github.com/astral-sh/uv)

#### **Option 1: Install from PyPI (Recommended)**

1. **Install the package:**
   ```bash
   uv pip install code-scope-mcp
   ```

2. **Add to your MCP configuration** (e.g., `claude_desktop_config.json`, `~/.claude.json`, or VS Code settings):

   ```json
   {
     "mcpServers": {
       "code-scope": {
         "command": "uvx",
         "args": ["code-scope-mcp"]
       }
     }
   }
   ```

#### **Option 2: Development Setup**

For contributing or local development:

1. **Clone and install:**
   ```bash
   git clone https://github.com/marksolly/code-scope-mcp.git
   cd code-scope-mcp
   uv sync
   ```

2. **Configure for local development:**
   ```json
   {
  "mcpServers": {
    "code-scope-dev": {
      "disabled": false,
      "timeout": 60,
      "command": "uv",
      "args": [
        "run",
        "code-scope-mcp"
      ],
      "cwd": "/insert/path/to/code-index-mcp",
      "type": "stdio"
    }
   }
   ```

3. **Debug with MCP Inspector:**

   ```bash
   npx @modelcontextprotocol/inspector uv run code-scope-mcp
   ```

#### **Configuration Examples**

See [`mcp_config_example.json`](mcp_config_example.json) for basic configuration and [`mcp_config_alternatives.md`](mcp_config_alternatives.md) for alternative setups.
#### **Database Setup**

The MCP server requires a path to a SQLite database containing the code index. You'll need to:

1. **Create/index your codebase** using the existing CLI tools in this project
2. **Specify the database path** when calling the `find_symbols` tool

Example tool call:
```json
{
  "db_path": "/path/to/your/code-index.db",
  "pattern": "User",
  "symbol_type": ["class"]
}
```

### **Available MCP Tools**

- **`find_symbols`**: Search for code symbols with advanced filtering and relationship analysis
  - Supports glob/regex patterns
  - Filter by symbol type, language, file path
  - Includes contextual information (relationships, properties, location)
  - Returns formatted results optimized for AI consumption

## Usage Examples

### **Quick Start Workflow**

**1. Initialize Your Project**

Build the initial index and tell the MCP server where the codebase is located.

Ask your coding assistant to:

```
Set the code-scope project path to /Users/dev/my-react-app and generate a log file.
```

*Automatically indexes your codebase and creates searchable cache while generating an .indexer.log file for you to verify*

## File Filtering & .indexerignore

Code Scope MCP includes **built-in default ignore rules** that automatically exclude common unwanted files and directories:

### Default Ignore Patterns
The following patterns are filtered by default during both **index** and **update** operations:
- Build artifacts: `dist/`, `build/`, `target/`, `out/`
- Dependencies: `node_modules/`, `venv/`, `env/`, `packages/`
- Python bytecode: `__pycache__/`, `*.pyc`, `*.pyo`
- IDE files: `.vscode/`, `.idea/`, `*~`
- Logs and temp files: `*.log`, `logs/`, `*.tmp`
- And many more...

### Custom .indexerignore Files

You can override or extend these defaults with `.indexerignore` files. **Custom ignore files take precedence over defaults**, but defaults still apply to files not explicitly covered by `.indexerignore` rules. Create an empty `.indexerignore` file if you want to disable defaults completely.

**Placement**: `.indexerignore` files work like `.gitignore` - they affect the directory they are placed in and all subdirectories.

**Pattern Support**: Gitignore-style patterns including:
- `pattern/` - Ignore entire directories
- `*.ext` - Ignore files by extension
- `!important.txt` - Include previously ignored files
- `# comments` - Comments are supported

**⚖️ Precedence Rules**:
1. **Custom .indexerignore files always take precedence** over defaults
2. Parent directory ignore files are checked if no local ignore file exists
3. If no `.indexerignore` files apply to a file path, **default rules are applied**
4. Defaults attempt to prevent accidental over-indexing but may not suit your project.

### Examples

**Example 1: Override defaults for documentation**
```bash
# .indexerignore in project root
# Include documentation that defaults would normally exclude
!docs/
!README.md
```

**Example 2: Additional project-specific exclusions**
```bash
# .indexerignore in project root
/cache/
/build/
/*.test.js
```

**Example 3: Directory-specific ignores**
```bash
# .indexerignore in src/ directory
/utils/temp/
/**/debug.*
```

### Behavior Notes

- **Index operations**: If no `.indexerignore` exists in the base directory, a warning is shown and defaults are used
- **Update operations**: Uses the same ignore logic as index operations for consistency
- **Performance**: Previously discovered `.indexerignore` files are cached for faster subsequent operations
- **No persistence**: Only file paths (not contents) are cached - `.indexerignore` files are always read fresh

## MCP Tool Usage Examples

The `find_symbols` MCP tool provides fast, token-efficient code search with relationship analysis.

### **Tool Parameters**

```json
{
  "db_path": "/path/to/code-index.db",
  "pattern": "search_pattern",
  "match_mode": "glob|regex",
  "case_sensitive": false,
  "symbol_type": ["function", "class", "method", "constant", "variable"],
  "path_pattern": "**/*.py",
  "language": "python",
  "limit": 100,
  "include_context": ["all", "location", "properties", "relationships"]
}
```

### **Example 1: Discovering Core Components**

* **User Request**: "I'm new to this user management system. Can you tell me which are the most important classes in this project?"
* **AI Assistant Tool Call**:
  ```json
  {
    "db_path": "/path/to/project/code-index.db",
    "pattern": "class*",
    "symbol_type": ["class"],
    "limit": 200
  }
  ```

  **Result**: Quick overview of all class definitions like `Person`, `User`, `UserRole`, `UserStatus`, `UserManager`, etc.

### **Example 2: Locating Specific Functionality**

* **User Request**: "I need to find where user creation logic is implemented."
* **AI Assistant Tool Call**:
  ```json
  {
    "db_path": "/path/to/project/code-index.db",
    "pattern": "create*",
    "symbol_type": ["function"],
    "include_context": ["relationships"]
  }
  ```

  **Result**: Pinpoints functions like `create_user` with their relationships and locations.

### **Example 3: File-Specific Analysis**

* **User Request**: "Show me all functions in the auth_service.py file."
* **AI Assistant Tool Call**:
  ```json
  {
    "db_path": "/path/to/project/code-index.db",
    "pattern": "*",
    "path_pattern": "**/auth_service.py",
    "symbol_type": ["function"],
    "include_context": ["all"]
  }
  ```

  **Result**: Complete function list with parameters, relationships, and usage context.

### **Example 4: Method Analysis**

* **User Request**: "What methods are available in the User class?"
* **AI Assistant Tool Call**:
  ```json
  {
    "db_path": "/path/to/project/code-index.db",
    "pattern": "*",
    "symbol_type": ["method"],
    "include_context": ["relationships"],
    "path_pattern": "**/user*.py"
  }
  ```

  **Result**: All User class methods with inheritance and call relationships.

### **Self-Analyzing Examples: Code Scope Indexing Itself**

These examples demonstrate the CLI tool analyzing its own codebase, showcasing the same underlying indexing capabilities that power the MCP server. The CLI provides direct access to the technology that enables AI assistants to understand complex codebases with token-efficient, relationship-aware search.

**Why CLI Examples Matter**: The CLI tool uses identical indexing technology as the MCP server, so these examples show the depth of code understanding available to AI assistants through the MCP interface.

#### **Example: Inheritance Hierarchy Analysis**

**Query**: Find all base relationship handler classes
```bash
uv run python cli.py query "Base*" --symbol-type class --limit 3
```

**Result**:
```text
[class] BaseFileFunctionCallHandler
  in: src/code_scope_mcp/indexing/relationship_handlers/common/base_file_function_call_handler.py
  has_method: __init__, extract_from_ast, _get_function_call_queries, _extract_function_from_node, resolve_immediate, _find_function_through_imports, resolve_complex
  inherits: BaseRelationshipHandler
  declared_by: base_file_function_call_handler.py
  imported_by: file_function_call_handler.py, file_function_call_handler.py, file_function_call_handler.py

[class] BaseImportHandler
  in: src/code_scope_mcp/indexing/relationship_handlers/common/base_import_handler.py
  has_method: __init__, extract_from_ast, _get_import_queries, _extract_import_from_node, _convert_module_to_file_path, resolve_immediate, _resolve_import_target, resolve_complex
  inherits: BaseRelationshipHandler
  declared_by: base_import_handler.py
  imported_by: import_handler.py, import_handler.py, import_handler.py

[class] BaseInheritsHandler
  in: src/code_scope_mcp/indexing/relationship_handlers/common/base_inherits_handler.py
  has_method: __init__, extract_from_ast, resolve_immediate, _resolve_inheritance_target, resolve_complex, _get_inheritance_symbol_types
  inherits: BaseRelationshipHandler
  declared_by: base_inherits_handler.py
  imported_by: inherits_handler.py, inherits_handler.py, inherits_handler.py
```

This reveals the correct inheritance hierarchy where multiple specialized handlers inherit from `BaseRelationshipHandler`, showing how the indexing system is architected with proper separation of concerns.

#### **Example: Language Definition Inheritance**

**Query**: Examine language-specific implementations
```bash
uv run python cli.py query "*" --symbol-type class --path-pattern "**/languages.py"
```

**Result**:
```text
[class] JavascriptLanguageDefinition
  in: src/code_scope_mcp/indexing/languages.py
  has_method: language_name, file_extensions, supported_symbol_types, supported_relationship_types
  inherits: LanguageDefinition
  declared_by: languages.py

[class] LanguageDefinition
  in: src/code_scope_mcp/indexing/languages.py
  has_method: language_name, file_extensions, supported_symbol_types, supported_relationship_types
  declared_by: languages.py
  imported_by: writer.py, orchestrator.py

[class] PhpLanguageDefinition
  in: src/code_scope_mcp/indexing/languages.py
  has_method: language_name, file_extensions, supported_symbol_types, supported_relationship_types
  inherits: LanguageDefinition
  declared_by: languages.py

[class] PythonLanguageDefinition
  in: src/code_scope_mcp/indexing/languages.py
  has_method: language_name, file_extensions, supported_symbol_types, supported_relationship_types
  inherits: LanguageDefinition
  declared_by: languages.py
```

This demonstrates the clean inheritance pattern where language-specific implementations (`JavascriptLanguageDefinition`, `PythonLanguageDefinition`, etc.) properly inherit from the base `LanguageDefinition` class.

#### **Example: Complex Method Orchestration**

**Query**: Analyze the core file processing workflow
```bash
uv run python cli.py query "process_files" --symbol-type method --limit 1
```

**Result**:
```text
[method] IndexingOrchestrator.process_files
  in: src/code_scope_mcp/indexing/orchestrator.py
  instantiates: IndexWriter, IndexReader, time_block, time_block, time_block
  calls: IndexingLogger.mustLog, IgnoreHandler.is_ignored, IndexingLogger.mustLog, IndexingLogger.start_timing, IndexingLogger.mustLog, IndexingOrchestrator._get_language_definition, IndexWriter.set_language_definition, IndexingOrchestrator.run_phase_1_symbol_extraction, IndexingOrchestrator._handle_exception, IndexingOrchestrator.run_phase_1_symbol_extraction, IndexingLogger.mustLog, IndexingLogger.mustLog, IndexingOrchestrator._get_language_definition, IndexWriter.set_language_definition, IndexingOrchestrator.run_phase_2_intermediate_resolution, IndexingOrchestrator._handle_exception, IndexingOrchestrator.run_phase_2_intermediate_resolution, IndexingLogger.mustLog, IndexingLogger.mustLog, IndexingOrchestrator._get_language_definition, IndexWriter.set_language_definition, IndexingOrchestrator.run_phase_3_final_resolution, IndexingOrchestrator._handle_exception, IndexingOrchestrator.run_phase_3_final_resolution, IndexingLogger.mustLog, IndexingLogger.stop_timing, IndexingLogger.print_profiling_report, IndexingOrchestrator._generate_exception_summary, IndexingLogger.mustLog
```

This reveals the sophisticated orchestration within `process_files`, showing instantiation of core components (`IndexWriter`, `IndexReader`) and the three-phase indexing pipeline with comprehensive error handling and performance monitoring.

**3. Analyze Key Files**

```
Give me a summary of src/api/userService.ts
```

*Uses: `get_file_summary` to show functions, imports, and complexity*

<details>

<summary><strong>Auto-refresh Configuration</strong></summary>

```
Configure automatic index updates when files change
```

*Uses: `configure_file_watcher` to enable/disable monitoring and set debounce timing*

</details>

<details>
<summary><strong>Project Maintenance</strong></summary>

```
I added new components, please refresh the project index
```

*Uses: `refresh_index` to update the searchable cache*

</details>

## Available MCP Tools

### **Symbol Search & Analysis**

| Tool | Description |
|------|-------------|
| **`find_symbols`** | Advanced code symbol search with relationship analysis<br>• Supports glob/regex patterns<br>• Filter by symbol type, language, file path<br>• Includes contextual relationships and properties<br>• Token-efficient formatted results |

### **Tool Parameters**

The `find_symbols` tool accepts these parameters:

- **`db_path`** (required): Path to SQLite database containing code index
- **`pattern`** (required): Search pattern (glob wildcards: `*` `?`)
- **`match_mode`**: `"glob"` (default) or `"regex"`
- **`case_sensitive`**: `false` (default) or `true`
- **`symbol_type`**: Array of symbol types to filter by
  - `"function"`, `"class"`, `"method"`, `"constant"`, `"variable"`
  - `"file"`, `"import"`, `"global"`, `"export"`, `"namespace"`
  - `"struct"`, `"typedef"`, `"enum"`
- **`path_pattern`**: Glob pattern to filter files (e.g., `"**/*.py"`)
- **`language`**: Programming language filter (e.g., `"python"`, `"javascript"`)
- **`limit`**: Maximum results (default: 50, max: 1000)
- **`include_context`**: Context to include
  - `"all"`: Include everything
  - `"location"`: File location and line numbers
  - `"properties"`: Symbol properties/metadata
  - `"relationships"`: Function calls, inheritance, etc.

## Troubleshooting

### **Auto-refresh Not Working**

If automatic index updates aren't working when files change, try:

- `pip install watchdog` (may resolve environment isolation issues)
- Use manual refresh: Call the `refresh_index` tool after making file changes
- Check file watcher status: Use `get_file_watcher_status` to verify monitoring is active

## Development & Contributing

### **Building from Source**

```bash
git clone https://github.com/marksolly/code-scope-mcp.git
cd code-scope-mcp
uv sync
uv run code-scope-mcp
```

### **Debugging**

```bash
npx @modelcontextprotocol/inspector uvx code-scope-mcp
```

### **Contributing**

Contributions are welcome!

Please open an issue with "Proposal:" in the title to discuss what you would like to contribute. Pre-planning is important because volunteer developer time is precious and we should not waste it.

**New Languages**
Please see [NEW_LANG_GUIDE.md](NEW_LANG_GUIDE.md) for details on how to add and run tests for new languages.

### Similar Projects

* https://glean.software/docs/introduction/ (for humans, not an MCP)
* https://github.com/johnhuang316/code-index-mcp
* https://github.com/admica/FileScopeMCP

### **Credit & Acknowledgement**

This MCP was originally forked from https://github.com/johnhuang316/code-index-mcp. Both this and the original repo have diverged wildly with completely different architectures. However, the original author provided inspiration and a starting point for this project. Thank you.

---

### **License**

[MIT License](LICENSE)

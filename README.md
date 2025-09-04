# Code Scope MCP

## WORK IN PROGRESS
This project is not in a running state yet.

The descriptions below are a vision statement.

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

Code Scope MCP is a [Model Context Protocol](https://modelcontextprotocol.io) server that bridges the gap between AI models and complex codebases.

When codebases grow large or when working across multiple repos it can be difficult for AI code assistants to understand the full scope of requests or the full impact of changes they make.

This MCP server maintains an index your code base and makes fast, token efficient, code-graph search and reporting tools available.

## Interfaces

Code Scope provides two ways to access its powerful code indexing capabilities:

### **MCP Server (Primary Interface)**
- **For AI Coding Assistants**: Designed to be integrated into AI tools like Claude Code and Cline
- **Contextual Search**: Provides AI assistants with deep code understanding and relationship analysis
- **Token Efficient**: Delivers comprehensive code insights without burning through token limits
- **Real-time Analysis**: Helps AI assistants understand code impact before making changes

### **CLI Tool (Direct Access)**
- **Standalone Usage**: Command-line interface for direct querying of indexed codebases
- **Same Technology**: Uses the identical indexing engine as the MCP server
- **Debugging & Analysis**: Useful for manual exploration and troubleshooting
- **Development**: Helps developers understand their codebase structure

Both interfaces share the same underlying index.

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

### **Recommended Setup (Most Users)**

Known to work with Claude Code and Cline. May work with others.

**Prerequisites:** Python 3.10+ and [uv](https://github.com/astral-sh/uv)

1. **Add to your MCP configuration** (e.g., `claude_desktop_config.json` or `~/.claude.json`):

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
2. **Restart your application** – `uvx` automatically handles installation and execution

### 🛠️ **Development Setup**

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
       "code-scope": {
         "command": "uv",
         "args": ["run", "code-scope-mcp"]
       }
     }
   }
   ```
3. **Debug with MCP Inspector:**

   ```bash
   npx @modelcontextprotocol/inspector uv run code-scope-mcp
   ```

<details>
<summary><strong>Alternative: Manual pip Installation</strong></summary>

If you prefer traditional pip management:

```bash
pip install code-scope-mcp
```

Then configure:

```json
{
  "mcpServers": {
    "code-scope": {
      "command": "code-scope-mcp",
      "args": []
    }
  }
}
```

</details>

## Usage Examples

### **Quick Start Workflow**

**1. Initialize Your Project**

Build the initial index and tell the MCP server where the codebase is located.

Ask your coding assistant to:

```
Set the code-scope project path to /Users/dev/my-react-app and generate a log file.
```

*Automatically indexes your codebase and creates searchable cache while generating an .indexer.log file for you to verify*

- **🚫 `.indexerignore` Support**: Create this file in your project root to exclude files and directories from indexing and search using gitignore-style patterns.

## Find Context Fast

To quickly understand and navigate this project's codebase using an AI code assistant, leverage the `find_symbols` tool for its speed and efficiency in identifying code structures.

This tool returns a dense, token efficient representation of how the matching symbols relate to the overall codebase.

### Example 1: Discovering Core Components

* **User Request to AI**: "I'm new to this user management system. Can you tell me which are the most important classes in this project?"
* **AI Assistant Tool Usage**:
  ```
  find_symbols pattern="class*" symbol_type=["class"]
  ```

  This provides a quick overview of all class definitions, such as `Person`, `User`, `UserRole`, `UserStatus`, `UserManager`, `AuthService`, etc., helping the user grasp the core building blocks.

### Example 2: Locating Specific Functionality

* **User Request to AI**: "I need to find where user creation logic is implemented. Look for functions related to creating users."
* **AI Assistant Tool Usage**:
  ```
  find_symbols pattern="create*" symbol_type=["function"]
  ```

  This would pinpoint functions like `create_user` within `user_manager.py`, allowing the user to quickly locate the relevant code for user creation.

**Example 3: Exploring File-Specific Logic

* **User Request to AI**: "Show me all the functions defined in the `auth_service.py` file to understand the authentication mechanisms."
* **AI Assistant  Tool Usage**:
  ```bash
  find_symbols pattern="*" path_pattern="**/auth_service.py" symbol_type=["function"]
  ```

  This narrows down the search to functions within a specific file, revealing authentication-related functions like `authenticate`, `login`, `logout`, `create_session`, etc.

### Example 4: Identifying Method Definitions within a Class

* **User Request to AI**: "I'm looking at the `User` class. What methods are defined within it, particularly around password management?"
* **AI Assistant Action**:
  ```bash
  find_symbols pattern="User.*" symbol_type=["method"] # Assuming 'method' is a discoverable type or part of a class name
  # Or, if methods are listed under classes:
  find_symbols pattern="set_password|check_password" symbol_type=["function"]
  ```

  This helps in discovering methods like `set_password`, `check_password`, etc., directly associated with the `User` class or its functionality.

By using these `find_symbols` commands, an AI assistant can efficiently guide a user through the codebase, helping them quickly locate relevant classes, functions, and methods based on their specific queries.

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

## Available Tools

### **Project Management**


| Tool                    | Description                                   |
| ------------------------- | ----------------------------------------------- |
| **`set_project_path`**  | Initialize indexing for a project directory   |
| **`refresh_index`**     | Rebuild the project index after file changes  |
| **`get_settings_info`** | View current project configuration and status |

### **Search & Discovery**


| Tool                       | Description                                                 |
| ---------------------------- | ------------------------------------------------------------- |
| **`search_code_advanced`** | Smart search with regex, fuzzy matching, and file filtering |
| **`find_files`**           | Locate files using glob patterns (e.g.,`**/*.py`)           |
| **`get_file_summary`**     | Analyze file structure, functions, imports, and complexity  |

### **Monitoring & Auto-refresh**


| Tool                          | Description                                        |
| ------------------------------- | ---------------------------------------------------- |
| **`get_file_watcher_status`** | Check file watcher status and configuration        |
| **`configure_file_watcher`**  | Enable/disable auto-refresh and configure settings |

### **System & Maintenance**


| Tool                        | Description                                             |
| ----------------------------- | --------------------------------------------------------- |
| **`create_temp_directory`** | Set up storage directory for index data                 |
| **`check_temp_directory`**  | Verify index storage location and permissions           |
| **`clear_settings`**        | Reset all cached data and configurations                |
| **`refresh_search_tools`**  | Re-detect available search tools (ugrep, ripgrep, etc.) |

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

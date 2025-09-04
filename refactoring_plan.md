# Code-Scope-MCP Refactoring Plan

## Executive Summary

This document outlines a comprehensive refactoring plan to rename the project from `code-index-mcp` to `code-scope-mcp`. This includes renaming the Python package, updating all references throughout the codebase, updating configuration files, and renaming the GitHub repository.

**Scope**: Complete project rename with no backward compatibility maintained.

**Risk Level**: High - This refactoring affects the core package structure, imports, and project identity.

**Estimated Time**: 2-3 hours for implementation, plus repository rename coordination.

## Requirements

### Functional Requirements
- [x] Rename project from `code-index-mcp` to `code-scope-mcp`
- [x] Rename main package directory from `src/code_index_mcp/` to `src/code_scope_mcp/`
- [x] Update all Python import statements
- [x] Update CLI entry point from `code-index-mcp` to `code-scope-mcp`
- [x] Update project configuration files
- [x] Update documentation and references
- [x] Rename GitHub repository
- [x] Update Git remote URLs

### Non-Functional Requirements
- [x] No backward compatibility maintained
- [x] All references to old name removed
- [x] Project functionality preserved
- [x] No exclusions from renaming scope

## High Level Plan

### Phase 1: Preparation
1. Create backup of current state
2. Analyze all references to old name
3. Plan the rename sequence to avoid breaking dependencies

### Phase 2: Core Package Rename
1. Rename `src/code_index_mcp/` to `src/code_scope_mcp/`
2. Update all import statements in Python files
3. Update package references in configuration files

### Phase 3: Project Configuration
1. Update `pyproject.toml` (name, scripts, URLs)
2. Update Git configuration and remote URLs
3. Update documentation files

### Phase 4: Repository Management
1. Rename GitHub repository
2. Update all repository references
3. Update CI/CD configurations if any

### Phase 5: Testing and Validation
1. Verify all imports work correctly
2. Test CLI functionality
3. Validate project builds and runs
4. Update any dependent documentation

## Relevant Files for Context

### Core Package Files
- `src/code_index_mcp/__init__.py` - Package initialization
- `src/code_index_mcp/server.py` - Main server implementation
- `src/code_index_mcp/__main__.py` - Main entry point
- All files in `src/code_index_mcp/` subdirectories

### Configuration Files
- `pyproject.toml` - Project metadata and dependencies
- `.git/config` - Git repository configuration
- `uv.lock` - Dependency lock file
- `requirements.txt` - Python dependencies

### Documentation Files
- `README.md` - Main project documentation
- `NEW_LANG_GUIDE.md` - Language support guide
- `parser_replaement_project.md` - Parser documentation

### Development Files
- `run.py` - Development runner script
- `cli.py` - CLI interface
- `test/test_language_support_suite.py` - Test suite

### Generated/Virtual Environment Files
- `.venv/` directory contents
- `code_index.db` - Project database
- `test_code_index.db` - Test database

## Unknowns, Risks & Assumptions

### Risks
- **High Risk**: Package directory rename could break all imports simultaneously
- **Medium Risk**: GitHub repository rename may affect existing clones and forks
- **Medium Risk**: Virtual environment may need recreation
- **Low Risk**: Some references in git history may persist

### Assumptions
- All team members will update their local clones after repository rename
- No external dependencies reference the old package name
- GitHub repository rename will be successful
- No CI/CD pipelines depend on the old repository name

### Dependencies
- GitHub repository rename must be coordinated with team
- All developers must update their local repository remotes
- Virtual environments may need recreation
- Any published packages may need republishing

## SQL DDL Statements

No SQL DDL changes required for this refactoring.

## Detailed Implementation Checklist

### Phase 1: Preparation & Analysis
- [x] Create full project backup/archive
- [x] Document current Git remote URLs and branches
- [x] Verify all team members are aware of upcoming rename
- [x] Create list of all files containing "code-index-mcp" references

#### Files Containing "code-index-mcp" References (78 total):
**Virtual Environment Files (.venv/):**
- `.venv/pyvenv.cfg` (prompt)
- `.venv/bin/activate` (VIRTUAL_ENV path, VIRTUAL_ENV_PROMPT)
- `.venv/bin/activate.nu` (virtual_env path, virtual_env_prompt)
- `.venv/bin/dotenv` (shebang path)
- `.venv/bin/mcp` (shebang path)
- `.venv/bin/activate_this.py` (VIRTUAL_ENV_PROMPT)
- `.venv/bin/activate.fish` (VIRTUAL_ENV path, VIRTUAL_ENV_PROMPT)
- `.venv/bin/activate.csh` (VIRTUAL_ENV path, VIRTUAL_ENV_PROMPT)
- `.venv/bin/activate.bat` (VIRTUAL_ENV path, VIRTUAL_ENV_PROMPT)
- `.venv/bin/watchmedo` (shebang path)
- `.venv/bin/httpx` (shebang path)
- `.venv/bin/code-index-mcp` (shebang path, script name)
- `.venv/bin/activate.ps1` (VIRTUAL_ENV_PROMPT)
- `.venv/bin/uvicorn` (shebang path)
- `.venv/lib/python3.11/site-packages/code_index_mcp-1.2.1.dist-info/entry_points.txt` (entry point)
- `.venv/lib/python3.11/site-packages/__editable__.code_index_mcp-1.2.1.pth` (editable install path)
- `.venv/lib/python3.11/site-packages/code_index_mcp-1.2.1.dist-info/METADATA` (package name, URLs)
- `.venv/lib/python3.11/site-packages/code_index_mcp-1.2.1.dist-info/RECORD` (file paths)
- `.venv/lib/python3.11/site-packages/code_index_mcp-1.2.1.dist-info/direct_url.json` (local path)

**Core Project Files:**
- `pyproject.toml` (project name, URLs, script entry point)
- `src/code_index_mcp/__main__.py` (docstring)
- `refactoring_plan.md` (documentation)
- `uv.lock` (project name, version)

**Documentation Files:**
- `README.md` (repository URLs, credit section)
- `NEW_LANG_GUIDE.md` (virtual environment path)
- `parser_replaement_project.md` (installation commands, repository URLs)

**Git Configuration:**
- `.git/config` (remote URL)
- `.git/FETCH_HEAD` (branch references)
- `.git/logs/HEAD` (clone URL)
- `.git/logs/refs/heads/master` (clone URL)
- `.git/logs/refs/remotes/origin/HEAD` (clone URL)

**Test Files:**
- `test/test_language_support_suite.py` (virtual environment path)

### Phase 2: Core Package Structure Changes
- [x] Rename directory `src/code_index_mcp/` to `src/code_scope_mcp/`
- [x] Update all Python import statements from `code_index_mcp` to `code_scope_mcp`
- [x] Update relative imports within the package
- [x] Update package references in `__init__.py` files
- [x] Update package references in `server.py` (keep internal indexer component names)
- [x] Update package references in `__main__.py`
- [x] Update package references in all service files
- [x] Update package references in all utility files
- [x] Update package references in all test files

**Note**: Internal components that are functionally indexers (CodeIndexerContext, IndexService, etc.) will retain their "indexer" naming for technical accuracy, while external branding uses "Code Scope".

### Phase 3: Project Configuration Updates
- [x] Update `pyproject.toml`:
  - [x] Change `name` from "code-index-mcp" to "code-scope-mcp"
  - [x] Change script entry point from "code-index-mcp" to "code-scope-mcp"
  - [x] Update Homepage URL to new repository
  - [x] Update Bug Tracker URL to new repository
- [x] Update Git configuration:
  - [x] Change remote URL in `.git/config`
  - [x] Update any branch configurations
- [x] Update `uv.lock` references (regenerate after changes)
- [x] Update `requirements.txt` if needed

### Phase 4: Documentation Updates
- [x] Update `README.md`:
  - [x] Change title from "Code Index MCP" to "Code Scope MCP"
  - [x] Update all repository URLs
  - [x] Update installation commands
  - [x] Update configuration examples
  - [x] Update credit/acknowledgment section
- [x] Update `NEW_LANG_GUIDE.md`:
  - [x] Update virtual environment paths
  - [x] Update any repository references
- [x] Update any inline documentation comments

### Phase 5: Development Environment Updates
- [x] Update `run.py`:
  - [x] Update import statement
  - [x] Update error messages and paths
- [x] Update `cli.py`:
  - [x] Update import statement
  - [x] Update any hardcoded references
- [x] Update test files:
  - [x] Update import statements in all test files
  - [x] Update any test data or fixtures
  - [x] Update test configuration

### Phase 6: Repository Management
- [ ] Rename GitHub repository from "code-index-mcp" to "code-scope-mcp"

### Phase 7: Virtual Environment & Dependencies
- [ ] Recreate virtual environment to use new package name
- [ ] Update any installed package references
- [ ] Clear any cached bytecode (.pyc files)

### Phase 8: Validation & Testing
- [x] Test CLI command `code-scope-mcp` functionality
- [x] Run test suite to ensure no regressions
- [ ] Verify Git operations work with new remote

### Phase 9: Communication & Documentation
- [ ] Publish package so it can be automatically installed with  `uv run code-scope-mcp`.

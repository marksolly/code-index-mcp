"""
Service layer for the Code Scope MCP server.

This package contains domain-specific services that handle the business logic
for different areas of functionality:

- ProjectService: Project initialization and configuration management
- IndexService: Index building, management, and file discovery
- SearchService: Code search operations and search tool management
- FileService: File operations, content retrieval, and analysis
- SettingsService: Settings management and directory operations

Each service follows a consistent pattern:
- Constructor accepts MCP Context parameter
- Methods correspond to MCP entry points
- Clear domain boundaries with no cross-service dependencies
- Shared utilities accessed through utils module
- Meaningful exceptions raised for error conditions
"""

from .base_service import BaseService
from .project_service import ProjectService
from .index_service import IndexService
from .search_service import SearchService
from .file_service import FileService
from .settings_service import SettingsService
from .file_watcher_service import FileWatcherService

__all__ = [
    'BaseService',
    'ProjectService',
    'IndexService', 
    'SearchService',
    'FileService',
    'SettingsService',
    'FileWatcherService'
]

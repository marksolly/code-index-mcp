"""
Context access utilities and helpers.

This module provides convenient access to MCP Context data and common
operations that services need to perform with the context.
"""

import os
from typing import Optional
from mcp.server.fastmcp import Context


class ContextHelper:
    """
    Helper class for convenient access to MCP Context data.

    This class wraps the MCP Context object and provides convenient properties
    and methods for accessing commonly needed data like base_path, settings, etc.
    """

    def __init__(self, ctx: Context):
        """
        Initialize the context helper.

        Args:
            ctx: The MCP Context object
        """
        self.ctx = ctx

    @property
    def base_path(self) -> str:
        """
        Get the base project path from the context.

        Returns:
            The base project path, or empty string if not set
        """
        try:
            return self.ctx.request_context.lifespan_context.base_path
        except AttributeError:
            return ""

    @property
    def settings(self) -> Optional['ProjectSettings']:
        """
        Get the project settings from the context.

        Returns:
            The ProjectSettings instance, or None if not available
        """
        try:
            # Import here to avoid circular dependency
            from ..project_settings import ProjectSettings
            
            settings_instance = self.ctx.request_context.lifespan_context.settings
            if isinstance(settings_instance, ProjectSettings):
                return settings_instance
            return None
        except (AttributeError, ImportError):
            return None

    @property
    def file_count(self) -> int:
        """
        Get the current file count from the context.

        Returns:
            The number of indexed files, or 0 if not available
        """
        try:
            return self.ctx.request_context.lifespan_context.file_count
        except AttributeError:
            return 0

    @property
    def file_index(self) -> dict:
        """
        Get the file index from the context.

        Returns:
            The file index dictionary, or empty dict if not available
        """
        try:
            return getattr(self.ctx.request_context.lifespan_context, 'file_index', {})
        except AttributeError:
            return {}

    @property
    def index_cache(self) -> dict:
        """
        Get the index cache from the context.

        Returns:
            The index cache dictionary, or empty dict if not available
        """
        try:
            return getattr(self.ctx.request_context.lifespan_context, 'index_cache', {})
        except AttributeError:
            return {}

    def validate_base_path(self) -> bool:
        """
        Check if the base path is set and valid.

        Returns:
            True if base path is set and exists, False otherwise
        """
        base_path = self.base_path
        return bool(base_path and os.path.exists(base_path))

    def get_base_path_error(self) -> Optional[str]:
        """
        Get an error message if base path is not properly set.

        Returns:
            Error message string if base path is invalid, None if valid
        """
        if not self.base_path:
            return ("Project path not set. Please use set_project_path to set a "
                    "project directory first.")

        if not os.path.exists(self.base_path):
            return f"Project path does not exist: {self.base_path}"

        if not os.path.isdir(self.base_path):
            return f"Project path is not a directory: {self.base_path}"

        return None

    def update_file_count(self, count: int) -> None:
        """
        Update the file count in the context.

        Args:
            count: The new file count
        """
        try:
            self.ctx.request_context.lifespan_context.file_count = count
        except AttributeError:
            pass  # Context not available or doesn't support this operation

    def update_base_path(self, path: str) -> None:
        """
        Update the base path in the context.

        Args:
            path: The new base path
        """
        try:
            self.ctx.request_context.lifespan_context.base_path = path
        except AttributeError:
            pass  # Context not available or doesn't support this operation

    def update_settings(self, settings: 'ProjectSettings') -> None:
        """
        Update the settings in the context.

        Args:
            settings: The new ProjectSettings instance
        """
        try:
            # Import here to avoid circular dependency
            from ..project_settings import ProjectSettings

            if isinstance(settings, ProjectSettings):
                self.ctx.request_context.lifespan_context.settings = settings
        except (AttributeError, ImportError):
            pass  # Context not available or doesn't support this operation

    def clear_index_cache(self) -> None:
        """
        Clear the index cache in the context.
        """
        try:
            if hasattr(self.ctx.request_context.lifespan_context, 'file_index'):
                self.ctx.request_context.lifespan_context.file_index.clear()
            if hasattr(self.ctx.request_context.lifespan_context, 'index_cache'):
                self.ctx.request_context.lifespan_context.index_cache.clear()
        except AttributeError:
            pass

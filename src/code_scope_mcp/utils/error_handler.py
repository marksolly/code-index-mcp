"""
Decorator-based error handling for MCP entry points.

This module provides consistent error handling across all MCP tools, resources, and prompts.
"""

import functools
from typing import Any, Callable, Dict, Union


def handle_mcp_errors(return_type: str = 'str') -> Callable:
    """
    Decorator to handle exceptions in MCP entry points consistently.
    
    This decorator catches all exceptions and formats them according to the expected
    return type, providing consistent error responses across all MCP entry points.
    
    Args:
        return_type: The expected return type format
            - 'str': Returns error as string format "Error: {message}"
            - 'dict': Returns error as dict format {"error": "Operation failed: {message}"}
            - 'json': Returns error as JSON string with dict format
    
    Returns:
        Decorator function that wraps MCP entry points with error handling
        
    Example:
        @mcp.tool()
        @handle_mcp_errors(return_type='str')
        def set_project_path(path: str, ctx: Context) -> str:
            return ProjectService(ctx).initialize_project(path)
            
        @mcp.tool()
        @handle_mcp_errors(return_type='dict')
        def search_code_advanced(pattern: str, ctx: Context, **kwargs) -> Dict[str, Any]:
            return SearchService(ctx).search_code(pattern, **kwargs)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Union[str, Dict[str, Any]]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_message = str(e)
                
                if return_type == 'dict':
                    return {"error": f"Operation failed: {error_message}"}
                elif return_type == 'json':
                    import json
                    return json.dumps({"error": f"Operation failed: {error_message}"})
                else:  # return_type == 'str' (default)
                    return f"Error: {error_message}"
        
        return wrapper
    return decorator


def handle_mcp_resource_errors(func: Callable) -> Callable:
    """
    Specialized error handler for MCP resources that always return strings.
    
    This is a convenience decorator specifically for @mcp.resource decorated functions
    which always return string responses.
    
    Args:
        func: The MCP resource function to wrap
        
    Returns:
        Wrapped function with error handling
        
    Example:
        @mcp.resource("config://code-indexer")
        @handle_mcp_resource_errors
        def get_config() -> str:
            ctx = mcp.get_context()
            return ProjectService(ctx).get_project_config()
    """
    return handle_mcp_errors(return_type='str')(func)


def handle_mcp_tool_errors(return_type: str = 'str') -> Callable:
    """
    Specialized error handler for MCP tools with flexible return types.
    
    This is a convenience decorator specifically for @mcp.tool decorated functions
    which may return either strings or dictionaries.
    
    Args:
        return_type: The expected return type ('str' or 'dict')
        
    Returns:
        Decorator function for MCP tools
        
    Example:
        @mcp.tool()
        @handle_mcp_tool_errors(return_type='dict')
        def find_files(pattern: str, ctx: Context) -> Dict[str, Any]:
            return IndexService(ctx).find_files_by_pattern(pattern)
    """
    return handle_mcp_errors(return_type=return_type)
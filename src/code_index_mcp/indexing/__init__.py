"""
Code indexing system for the MCP server.

This module provides structured code analysis, relationship tracking,
and enhanced search capabilities through a JSON-based index format.
"""

from .models import (
    FileInfo,
    FunctionInfo,
    ClassInfo,
    ImportInfo,
    FileAnalysisResult,
    CodeIndex
)

from .builder import IndexBuilder
from .scanner import ProjectScanner
from ..analyzers.manager import LanguageAnalyzerManager

__all__ = [
    'FileInfo',
    'FunctionInfo', 
    'ClassInfo',
    'ImportInfo',
    'FileAnalysisResult',
    'CodeIndex',
    'IndexBuilder',
    'ProjectScanner',
    'LanguageAnalyzerManager'
]

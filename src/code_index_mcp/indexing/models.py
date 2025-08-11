"""
Data models for the code indexing system.

This module defines the core data structures used throughout the indexing system,
including file information, code analysis results, and the complete index structure.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


@dataclass
class FileInfo:
    """Basic file information."""
    id: int
    path: str
    size: int
    modified_time: datetime
    extension: str
    language: str


@dataclass
class FunctionInfo:
    """Function definition information."""
    name: str
    qname: str
    parameters: List[str]
    line_start: int
    line_end: int
    line_count: int
    calls: List[str] = field(default_factory=list)
    called_by: List[str] = field(default_factory=list)
    is_async: bool = False
    decorators: List[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """Class definition information."""
    name: str
    qname: str
    line_start: int
    line_end: int
    line_count: int
    methods: List[FunctionInfo]
    inherits_from: Optional[str] = None
    instantiated_by: List[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """Import statement information."""
    module: str
    imported_names: List[str]
    import_type: str  # 'import', 'from', 'es6', etc.
    line_number: int


@dataclass
class FileAnalysisResult:
    """Complete analysis result for a single file."""
    file_info: FileInfo
    functions: List[FunctionInfo]
    classes: List[ClassInfo]
    imports: List[ImportInfo]
    language_specific: Dict[str, Any]
    analysis_errors: List[str] = field(default_factory=list)


@dataclass
class ProjectScanResult:
    """Result of project directory scanning."""
    directory_tree: Dict[str, Any]
    file_list: List[FileInfo]
    special_files: Dict[str, List[str]]
    project_metadata: Dict[str, Any]


@dataclass
class RelationshipGraph:
    """Graph of relationships between code elements."""
    function_calls: Dict[str, List[str]]
    class_instantiations: Dict[str, List[str]]
    import_relationships: Dict[str, List[str]]
    reverse_lookups: Dict[str, Any]


@dataclass
class CodeIndex:
    """Complete code index structure."""
    project_metadata: Dict[str, Any]
    directory_tree: Dict[str, Any]
    files: List[Dict[str, Any]]
    lookups: Dict[str, Any]
    reverse_lookups: Dict[str, Any]
    special_files: Dict[str, List[str]]
    index_metadata: Dict[str, Any]
    
    def to_json(self) -> str:
        """Convert index to JSON string."""
        # Convert datetime objects to ISO format strings
        def serialize_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        return json.dumps(self.__dict__, default=serialize_datetime, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'CodeIndex':
        """Create index from JSON string."""
        data = json.loads(json_str)
        
        # Convert ISO format strings back to datetime objects in project_metadata
        if 'indexed_at' in data.get('project_metadata', {}):
            data['project_metadata']['indexed_at'] = datetime.fromisoformat(
                data['project_metadata']['indexed_at']
            )
        
        return cls(**data)
    
    def get_version(self) -> str:
        """Get the indexing version."""
        return self.index_metadata.get('version', '1.0')
    
    def is_current_version(self) -> bool:
        """Check if this index uses the current version format."""
        return self.get_version() >= '4.0'


@dataclass
class LookupTables:
    """Forward lookup tables for efficient querying."""
    path_to_id: Dict[str, int]
    function_to_file_id: Dict[str, List[int]]  # Changed: now supports multiple files per function name
    class_to_file_id: Dict[str, List[int]]     # Changed: now supports multiple files per class name


@dataclass
class ReverseLookups:
    """Reverse lookup tables for relationship queries."""
    function_callers: Dict[str, List[Dict[str, Any]]]
    class_instantiators: Dict[str, List[Dict[str, Any]]]
    imports_module: Dict[str, List[int]]
    has_decorator: Dict[str, List[Dict[str, Any]]]


@dataclass
class SpecialFiles:
    """Categorized special files in the project."""
    entry_points: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    documentation: List[str] = field(default_factory=list)
    build_files: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of index validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

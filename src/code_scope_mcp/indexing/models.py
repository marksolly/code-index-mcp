from dataclasses import dataclass
from typing import Optional

@dataclass
class Symbol:
    """Represents a symbol found in the codebase."""
    name: str
    qname: str
    symbol_type: str
    file_path: str
    line_number: int
    language: str
    file_id: Optional[int] = None

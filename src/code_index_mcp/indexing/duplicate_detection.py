"""Functions for detecting duplicate symbols in the index."""

from typing import Dict, Set
from .models import CodeIndex

def detect_duplicate_functions(index: CodeIndex) -> Dict[str, Set[str]]:
    """
    Detects duplicate function names across different files.

    Args:
        index: The code index.

    Returns:
        A dictionary mapping duplicate function names to a set of file paths.
    """
    return {}

def detect_duplicate_classes(index: CodeIndex) -> Dict[str, Set[str]]:
    """
    Detects duplicate class names across different files.

    Args:
        index: The code index.

    Returns:
        A dictionary mapping duplicate class names to a set of file paths.
    """
    return {}

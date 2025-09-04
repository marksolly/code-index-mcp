"""Utilities for handling qualified names and paths."""

def normalize_file_path(file_path: str) -> str:
    """
    Normalize a file path by replacing backslashes with forward slashes.

    Args:
        file_path: The file path to normalize.

    Returns:
        The normalized file path.
    """
    if not file_path:
        return ""
    return file_path.replace("\\", "/")

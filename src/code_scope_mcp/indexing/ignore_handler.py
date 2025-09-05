import os
from pathlib import Path
from typing import List, Set, Optional, Tuple

from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern


class IgnoreHandler:
    """
    Handles file filtering based on .indexerignore rules (git-style).
    Searches up the directory tree for .indexerignore files.
    """

    MAX_CACHE_ENTRIES = 1000

    def __init__(self):
        self._ignore_cache: dict[str, Tuple[Optional[str], Optional[PathSpec]]] = {}

    def _prune_cache_if_needed(self):
        """Prune cache if it exceeds the maximum size."""
        if len(self._ignore_cache) >= self.MAX_CACHE_ENTRIES:
            self._ignore_cache.clear()

    def _find_ignore_file(self, start_path: str) -> Optional[str]:
        """Walk up from start_path looking for .indexerignore until hitting root."""
        current = Path(start_path).parent
        while current != current.parent:  # Not at filesystem root
            ignore_path = current / ".indexerignore"
            if ignore_path.exists():
                return str(ignore_path)
            current = current.parent
        return None

    def _get_ignore_spec(self, file_path: str) -> Tuple[Optional[str], Optional[PathSpec]]:
        """Get or create cached ignore spec for a file's directory."""
        file_dir = str(Path(file_path).parent)

        if file_dir not in self._ignore_cache:
            self._prune_cache_if_needed()
            ignore_file = self._find_ignore_file(file_path)
            if ignore_file:
                patterns = []
                try:
                    with open(ignore_file, "r", encoding="utf-8") as f:
                        patterns = [
                            line.strip() for line in f
                            if line.strip() and not line.startswith("#")
                        ]
                    spec = PathSpec.from_lines(GitWildMatchPattern, patterns)
                    self._ignore_cache[file_dir] = (ignore_file, spec)
                except Exception:
                    # If we can't read the ignore file, treat as no ignore file
                    self._ignore_cache[file_dir] = (None, None)
            else:
                self._ignore_cache[file_dir] = (None, None)

        return self._ignore_cache[file_dir]

    def is_ignored(self, file_path: str) -> bool:
        """
        Checks if a given file path should be ignored.
        Searches up the directory tree for .indexerignore files.

        Args:
            file_path: The absolute path to the file.

        Returns:
            True if the file should be ignored, False otherwise.
        """
        ignore_file, spec = self._get_ignore_spec(file_path)
        if not spec:
            return False  # No ignore file found

        # Compute relative path from ignore file directory
        ignore_dir = Path(ignore_file).parent
        relative_path = os.path.relpath(file_path, ignore_dir)
        return spec.match_file(relative_path)

import os
from typing import List, Set

from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern


class IgnoreHandler:
    """
    Handles file filtering based on .indexerignore rules (git-style).
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.ignore_file_path = os.path.join(project_root, ".indexerignore")
        self.spec = self._load_spec()

    def _load_spec(self) -> PathSpec:
        """Loads the .indexerignore file and compiles the patterns."""
        patterns = []
        if os.path.exists(self.ignore_file_path):
            with open(self.ignore_file_path, "r") as f:
                patterns = [
                    line for line in f.read().splitlines() if line and not line.startswith("#")
                ]
        return PathSpec.from_lines(GitWildMatchPattern, patterns)

    def is_ignored(self, file_path: str) -> bool:
        """
        Checks if a given file path should be ignored.

        Args:
            file_path: The absolute path to the file.

        Returns:
            True if the file should be ignored, False otherwise.
        """
        relative_path = os.path.relpath(file_path, self.project_root)
        return self.spec.match_file(relative_path)

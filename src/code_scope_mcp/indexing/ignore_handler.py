import os
import sys
from pathlib import Path
from typing import List, Set, Optional, Tuple

from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern


class IgnoreHandler:
    """
    Handles file filtering based on .indexerignore rules (git-style).
    Searches up the directory tree for .indexerignore files.

    If no .indexerignore file is found in the base directory being indexed,
    applies a standard set of ignore rules and outputs a warning.
    """

    MAX_CACHE_ENTRIES = 1000

    # Default ignore patterns to use when no .indexerignore file exists
    DEFAULT_IGNORE_PATTERNS = [
        # Version control
        ".git/",
        ".svn/",
        ".hg/",
        ".bzr/",

        # Dependencies and virtual environments
        "node_modules/",
        "venv/",
        "env/",
        "ENV/",
        ".venv/",
        ".env/",
        "lib/",
        "lib64/",
        "packages/",

        # Python-specific
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        ".Python",
        "build/",
        "develop-eggs/",
        "dist/",
        "downloads/",
        "eggs/",
        ".eggs/",
        "parts/",
        "sdist/",
        "var/",
        "*.egg-info/",
        ".installed.cfg",
        "*.egg",

        # JavaScript/Node.js
        "npm-debug.log*",
        "yarn-debug.log*",
        "yarn-error.log*",

        # Build artifacts
        "dist/",
        "build/",
        "target/",
        "out/",
        "bin/",
        "obj/",
        ".gradle/",
        ".next/",
        ".nuxt/",

        # Cache directories
        ".cache/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".tox/",

        # IDE and editor files
        ".vscode/",
        ".idea/",
        "*.swp",
        "*.swo",
        "*~",
        ".tmp/",

        # OS-specific files
        ".DS_Store",
        "Thumbs.db",
        ".Trashes/",
        "._*",

        # Temporary and backup files
        "*.tmp",
        "*.bak",
        "*.orig",
        "*.rej",
        ".#*",

        # Log files
        "*.log",
        "logs/",

        # Coverage reports
        ".coverage",
        "coverage.xml",
        "htmlcov/",

        # Package manager lock files (may be useful for analysis in some cases, but often excluded)
        # "package-lock.json",
        # "yarn.lock",
        # "Pipfile.lock",
    ]

    def __init__(self):
        self._ignore_cache: dict[str, Tuple[Optional[str], Optional[PathSpec]]] = {}
        self._default_spec: Optional[PathSpec] = None

        # Initialize registry dynamically, populated as ignore files are discovered
        self._ignore_registry = set()

        # Always setup default ignore rules for universal protection
        self._setup_default_ignore_rules()

    def _setup_default_ignore_rules(self):
        """Set up default ignore patterns when no .indexerignore file is found."""
        self._default_spec = PathSpec.from_lines(GitWildMatchPattern, self.DEFAULT_IGNORE_PATTERNS)

    def _prune_cache_if_needed(self):
        """Prune cache if it exceeds the maximum size."""
        if len(self._ignore_cache) >= self.MAX_CACHE_ENTRIES:
            self._ignore_cache.clear()

    def _find_ignore_file(self, start_path: str) -> Optional[str]:
        """Walk up from start_path looking for .indexerignore until hitting root."""
        # First check registry for known ignore files that could apply to this path
        file_path_obj = Path(start_path)

        for registry_path in self._ignore_registry:
            registry_path_obj = Path(registry_path)
            try:
                # Check if this registry ignore file could apply to our current path
                # (i.e., if start_path is within or at the same level as registry_path's parent)
                file_path_obj.relative_to(registry_path_obj.parent)
                # If we get here without exception, the registry path applies
                if registry_path_obj.exists():
                    return str(registry_path)
            except ValueError:
                # relative_to raises ValueError if not relative - this registry entry doesn't apply
                continue

        # Fall back to walking up directory tree
        current = Path(start_path).parent
        while current != current.parent:  # Not at filesystem root
            ignore_path = current / ".indexerignore"
            if ignore_path.exists():
                ignore_file_str = str(ignore_path)
                # Record this discovery for future reuse
                self.record_discovered_ignore_file(ignore_file_str)
                return ignore_file_str
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
        If no applicable .indexerignore file is found, applies default ignore rules.

        Args:
            file_path: The absolute path to the file.

        Returns:
            True if the file should be ignored, False otherwise.
        """
        ignore_file, spec = self._get_ignore_spec(file_path)

        if spec:
            # Custom .indexerignore file found - use its rules
            ignore_dir = Path(ignore_file).parent
            relative_path = os.path.relpath(file_path, ignore_dir)
            return spec.match_file(relative_path)
        elif self._default_spec:
            # No applicable .indexerignore file found - apply universal default rules
            # For defaults, match against the full path since they're meant to work anywhere
            return self._default_spec.match_file(file_path)
        else:
            # No ignore rules available
            return False

    def record_discovered_ignore_file(self, ignore_file_path: str):
        """
        Record that a .indexerignore file was discovered during indexing.
        This allows future commands to find ignore files more efficiently during this session.
        """
        self._ignore_registry.add(ignore_file_path)

    def get_registry(self) -> set[str]:
        """Get the current ignore file registry."""
        return self._ignore_registry.copy()

    def has_discovered_ignore_files(self) -> bool:
        """Check if any .indexerignore files were discovered during processing."""
        return len(self._ignore_registry) > 0

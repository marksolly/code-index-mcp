"""Language analyzer manager."""

from ..constants import EXTENSION_TO_LANGUAGE
from ..indexing.models import DebugOptions
from typing import Optional

class LanguageAnalyzerManager:
    def __init__(self, debug_options: Optional[DebugOptions] = None):
        self.analyzers = {}
        self.debug_options = debug_options or DebugOptions()

    def get_analyzer(self, file_path: str):
        from .tree_sitter_analyzer import TreeSitterAnalyzer
        
        extension = "." + file_path.split(".")[-1]
        lang_name = EXTENSION_TO_LANGUAGE.get(extension)
        if not lang_name:
            return None

        if lang_name not in self.analyzers:
            self.analyzers[lang_name] = TreeSitterAnalyzer(lang_name, self.debug_options)
        return self.analyzers[lang_name]

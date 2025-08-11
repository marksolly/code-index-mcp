"""Language analyzer manager."""

from ..constants import EXTENSION_TO_LANGUAGE

class LanguageAnalyzerManager:
    def __init__(self):
        self.analyzers = {}

    def get_analyzer(self, file_path: str):
        from .tree_sitter_analyzer import TreeSitterAnalyzer
        
        extension = "." + file_path.split(".")[-1]
        lang_name = EXTENSION_TO_LANGUAGE.get(extension)
        if not lang_name:
            return None

        if lang_name not in self.analyzers:
            self.analyzers[lang_name] = TreeSitterAnalyzer(lang_name)
        return self.analyzers[lang_name]

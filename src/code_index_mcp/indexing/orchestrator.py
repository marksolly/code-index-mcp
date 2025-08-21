import importlib
import pkgutil
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

from .ignore_handler import IgnoreHandler
from .indexing_logger import IndexingLogger
from .languages import LanguageDefinition 
from .reader import IndexReader
from .relationship_analyzers.base import BaseRelationshipAnalyzer
from .symbol_extractors.base import BaseSymbolExtractor
from .writer import IndexWriter


class IndexingOrchestrator:
    def __init__(self, project_root: str, db_connection: Optional[sqlite3.Connection] = None, logger: Optional[IndexingLogger] = None):
        self.project_root = project_root
        self.db_connection = db_connection or sqlite3.connect(":memory:")
        self.logger = logger or IndexingLogger(enabled=False)
        self.ignore_handler = IgnoreHandler(project_root)
        self.language_analyzers: Dict[str, List[Type[BaseRelationshipAnalyzer]]] = {}
        self.symbol_extractor_classes: Dict[str, Type[BaseSymbolExtractor]] = {}
        self.language_definitions: Dict[str, LanguageDefinition] = self._discover_language_definitions()

    def _discover_language_definitions(self) -> Dict[str, LanguageDefinition]:
        definitions = {}
        package_path = Path(__file__).parent / "languages.py"
        package_name = "src.code_index_mcp.indexing.languages"

        try:
            module = importlib.import_module(package_name)
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                if isinstance(attribute, type) and issubclass(attribute, LanguageDefinition) and attribute is not LanguageDefinition:
                    instance = attribute()
                    definitions[instance.language_name] = instance
        except ImportError as e:
            self.logger.mustLog("Orchestrator", f"Failed to import language definitions: {e}")
            raise e
        return definitions

    def _get_language_definition(self, language: str) -> LanguageDefinition:
        definition = self.language_definitions.get(language)
        if not definition:
            raise ValueError(f"Unsupported language or missing definition: {language}")
        return definition

    def _get_symbol_extractor_class(self, language: str) -> Type[BaseSymbolExtractor]:
        if language not in self.symbol_extractor_classes:
            try:
                module = importlib.import_module(f".{language}_extractor", package="src.code_index_mcp.indexing.symbol_extractors")
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type) and issubclass(attribute, BaseSymbolExtractor) and attribute is not BaseSymbolExtractor:
                        self.symbol_extractor_classes[language] = attribute
                        break
            except ImportError as e:
                self.logger.mustLog("Orchestrator", f"Failed to import symbol extractor for {language}: {e}")
                raise ValueError(f"Unsupported language or missing extractor: {language}")

        extractor_class = self.symbol_extractor_classes.get(language)
        if not extractor_class:
            raise ValueError(f"No symbol extractor found for language: {language}")
        return extractor_class

    def process_files(self, all_files: List[Tuple[str, str, str]]):
        """
        Orchestrates the multi-phase indexing process for a list of files,
        after filtering them using .indexerignore rules.
        """
        self.logger.mustLog("Orchestrator", "Starting file filtering and indexing process.")
        
        files_to_index = []
        scan_log = []
        for file_path, language, source_code in all_files:
            if self.ignore_handler.is_ignored(file_path):
                scan_log.append(f"- {file_path}")
            else:
                scan_log.append(f"+ {file_path}")
                files_to_index.append((file_path, language, source_code))
        
        # Output the scan log
        print("\n".join(scan_log))

        if not files_to_index:
            self.logger.mustLog("Orchestrator", "No files to index after filtering.")
            return

        writer = IndexWriter(self.db_connection, self.logger)
        reader = IndexReader(self.db_connection, self.logger)

        # Phase 1: Symbol Extraction for all files
        self.logger.mustLog("Orchestrator", "Beginning Phase 1: Symbol Extraction.")
        for file_path, language, source_code in files_to_index:
            language_definition = self._get_language_definition(language)
            self.logger.current_context['language'] = language
            self.logger.mustLog("Orchestrator", f"Extracting {language}")
            writer.set_language_definition(language_definition)
            self.run_phase_1_symbol_extraction(file_path, language, source_code, writer)
        writer.flush()
        self.logger.mustLog("Orchestrator", "Completed Phase 1 and flushed symbols.")

        # Phase 2: Intermediate Relationship Resolution
        self.logger.mustLog("Orchestrator", "Beginning Phase 2: Intermediate Resolution.")
        # Get all unique languages from the discovered language definitions
        unique_languages = list(self.language_definitions.keys())
        for lang in unique_languages:
            self.logger.current_context['language'] = lang
            language_definition = self._get_language_definition(lang)
            writer.set_language_definition(language_definition)
            self.run_phase_2_intermediate_resolution(writer, reader, lang)
        writer.flush()
        self.logger.mustLog("Orchestrator", "Completed Phase 2 and flushed relationships.")

        # Phase 3: Final Relationship Resolution
        self.logger.mustLog("Orchestrator", "Beginning Phase 3: Final Resolution.")
        for lang in unique_languages:
            self.logger.current_context['language'] = lang
            language_definition = self._get_language_definition(lang)
            writer.set_language_definition(language_definition)
            self.run_phase_3_final_resolution(writer, reader, lang)
        writer.flush()
        self.logger.mustLog("Orchestrator", "Completed multi-phase indexing process.")

    def run_phase_1_symbol_extraction(self, file_path: str, language: str, source_code: str, writer: IndexWriter):
        self.logger.set_context(file_path=file_path, language=language)
        self.logger.mustLog("Orchestrator", f"Extracting symbols for {file_path} ({language})")
        try:
            extractor_class = self._get_symbol_extractor_class(language)
            extractor = extractor_class(file_path, language, self.logger)
            extractor.extract_symbols(source_code, writer)
        except Exception as e:
            self.logger.mustLog("Orchestrator", f"Error during Phase 1 for {file_path}: {e}")
            raise

    def run_phase_2_intermediate_resolution(self, writer: IndexWriter, reader: IndexReader, language: str):
        self.logger.set_context(file_path="N/A", language=language)
        analyzers = self._get_relationship_analyzers(language, "phase_2")
        for analyzer_class in analyzers:
            analyzer = analyzer_class(language, self.logger)
            analyzer.find_relationships(writer, reader)

    def run_phase_3_final_resolution(self, writer: IndexWriter, reader: IndexReader, language: str):
        self.logger.set_context(file_path="N/A", language=language)
        self.logger.mustLog("Orchestrator", f"Starting Phase 3: Final Relationship Resolution for {language}")
        analyzers = self._get_relationship_analyzers(language, "phase_3")
        for analyzer_class in analyzers:
            analyzer = analyzer_class(language, self.logger)
            analyzer.find_relationships(writer, reader)
        self.logger.mustLog("Orchestrator", f"Phase 3: Final Resolution completed for {language}")

    def _get_relationship_analyzers(self, language: str, phase: str) -> List[Type[BaseRelationshipAnalyzer]]:
        # Caching analyzers per language and phase
        cache_key = f"{language}_{phase}"
        if cache_key in self.language_analyzers:
            return self.language_analyzers[cache_key]

        analyzers = {}
        language_definition = self._get_language_definition(language)
        generic_analyzers_to_use = language_definition.uses_generic_analyzers

        # Discover common analyzers, but only if they are in the opt-in list
        self._discover_analyzers("common", phase, analyzers, filter_by=generic_analyzers_to_use)

        # Discover language-specific analyzers for the given phase
        self._discover_analyzers(language, phase, analyzers)

        self.language_analyzers[cache_key] = list(analyzers.values())
        return self.language_analyzers[cache_key]

    def _discover_analyzers(self, language_or_common: str, phase: str, analyzers: dict, filter_by: Optional[List[str]] = None):
        package_path = Path(__file__).parent / "relationship_analyzers" / language_or_common / phase

        if not package_path.is_dir():
            return

        package_name = f"src.code_index_mcp.indexing.relationship_analyzers.{language_or_common}.{phase}"

        for _, module_name, _ in pkgutil.iter_modules([str(package_path)]):
            try:
                module = importlib.import_module(f".{module_name}", package=package_name)
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type) and issubclass(attribute, BaseRelationshipAnalyzer) and attribute is not BaseRelationshipAnalyzer:
                        # If a filter is provided, only include analyzers in the filter
                        if filter_by and attribute.__name__ not in filter_by:
                            continue

                        analyzer_key = attribute.relationship_type
                        if analyzer_key:
                            analyzers[analyzer_key] = attribute
            except ImportError as e:
                self.logger.mustLog("Orchestrator", f"Failed to import analyzer module {module_name}: {e}")
                raise e

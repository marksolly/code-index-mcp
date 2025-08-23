import importlib
import pkgutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from tree_sitter_languages import get_language, get_parser

from .ignore_handler import IgnoreHandler
from .indexing_logger import IndexingLogger
from .languages import LanguageDefinition
from .reader import IndexReader
from .relationship_handlers.base_relationship_handler import BaseRelationshipHandler
from .symbol_extractors.base_symbol_extractor import BaseSymbolExtractor
from .writer import IndexWriter


class IndexingOrchestrator:
    def __init__(self, project_root: str, db_connection: Optional[sqlite3.Connection] = None, logger: Optional[IndexingLogger] = None):
        self.project_root = project_root
        self.db_connection = db_connection or sqlite3.connect(":memory:")
        self.logger = logger or IndexingLogger(enabled=False)
        self.ignore_handler = IgnoreHandler(project_root)
        self.symbol_extractor_classes: Dict[str, Type[BaseSymbolExtractor]] = {}
        self.language_definitions: Dict[str, LanguageDefinition] = self._discover_language_definitions()

        # Cache tree-sitter parsers and language objects for efficiency
        self.parsers: Dict[str, Any] = {}
        self.language_objects: Dict[str, Any] = {}

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

    def _get_parser_and_language(self, language: str) -> Tuple[Any, Any]:
        """Get or create parser and language objects for a language (cached for efficiency)."""
        if language not in self.parsers:
            self.parsers[language] = get_parser(language)
            self.language_objects[language] = get_language(language)

        return self.parsers[language], self.language_objects[language]

    def _get_symbol_extractor_class(self, language: str) -> Type[BaseSymbolExtractor]:
        if language not in self.symbol_extractor_classes:
            try:
                module = importlib.import_module(f".{language}_symbol_extractor", package="src.code_index_mcp.indexing.symbol_extractors")
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
            writer.set_language_definition(language_definition)
            self.run_phase_1_symbol_extraction(file_path, language, source_code, writer)
        self.logger.mustLog("Orchestrator", "Completed Phase 1.")

        # Phase 2: Intermediate Relationship Resolution
        self.logger.mustLog("Orchestrator", "Beginning Phase 2: Intermediate Resolution.")
        # Get all unique languages from the discovered language definitions
        unique_languages = list(self.language_definitions.keys())
        for lang in unique_languages:
            self.logger.current_context['language'] = lang
            language_definition = self._get_language_definition(lang)
            writer.set_language_definition(language_definition)
            self.run_phase_2_intermediate_resolution(writer, reader, lang)
        self.logger.mustLog("Orchestrator", "Completed Phase 2.")

        # Phase 3: Final Relationship Resolution
        self.logger.mustLog("Orchestrator", "Beginning Phase 3: Final Resolution.")
        for lang in unique_languages:
            self.logger.current_context['language'] = lang
            language_definition = self._get_language_definition(lang)
            writer.set_language_definition(language_definition)
            self.run_phase_3_final_resolution(writer, reader, lang)
        self.logger.mustLog("Orchestrator", "Completed multi-phase indexing process.")

    def run_phase_1_symbol_extraction(self, file_path: str, language: str, source_code: str, writer: IndexWriter):
        """Phase 1: Extract symbols and create unresolved relationships"""
        self.logger.set_context(file_path=file_path, language=language)
        self.logger.mustLogForLang("Orchestrator", f"Extracting symbols for {file_path} ({language})")
        try:
            # Get cached parser and language objects for efficiency
            parser, language_obj = self._get_parser_and_language(language)

            # Create extractor with cached objects
            extractor_class = self._get_symbol_extractor_class(language)
            extractor = extractor_class(file_path, language, parser, language_obj, self.logger)

            # Parse AST once for efficiency
            tree = parser.parse(bytes(source_code, "utf8"))
            file_qname = extractor._get_file_qname(file_path)

            # Extract symbols using the pre-parsed tree
            extractor.extract_symbols(tree, writer, file_qname)

            # Extract unresolved relationships using self-describing handlers
            handlers = self._get_relationship_handlers(language)
            reader = IndexReader(self.db_connection, self.logger)
            for handler_class in handlers.values():
                handler = handler_class(language, language_obj, self.logger)
                handler.extract_from_ast(tree, writer, reader, file_qname)
        except Exception as e:
            self.logger.mustLog("Orchestrator", f"Error during Phase 1 for {file_path}: {e}")
            raise

    def run_phase_2_intermediate_resolution(self, writer: IndexWriter, reader: IndexReader, language: str):
        """Phase 2: Resolve relationships with current knowledge"""
        self.logger.set_context(file_path="N/A", language=language)
        handlers = self._get_relationship_handlers(language)

        # Sort handlers by phase dependencies
        sorted_handlers = self._sort_handlers_by_dependencies(handlers)

        for handler_class in sorted_handlers.values():
            _, language_obj = self._get_parser_and_language(language)
            handler = handler_class(language, language_obj, self.logger)
            handler.resolve_immediate(writer, reader)

    def run_phase_3_final_resolution(self, writer: IndexWriter, reader: IndexReader, language: str):
        """Phase 3: Complex multi-step relationship resolution"""
        self.logger.set_context(file_path="N/A", language=language)
        self.logger.mustLogForLang("Orchestrator", f"Starting Phase 3: Final Relationship Resolution for {language}")
        handlers = self._get_relationship_handlers(language)

        # Sort handlers by phase dependencies for complex resolution
        sorted_handlers = self._sort_handlers_by_dependencies(handlers)

        for handler_class in sorted_handlers.values():
            _, language_obj = self._get_parser_and_language(language)
            handler = handler_class(language, language_obj, self.logger)
            handler.resolve_complex(writer, reader)
        self.logger.mustLogForLang("Orchestrator", f"Phase 3: Final Resolution completed for {language}")


    def _get_relationship_handlers(self, language: str) -> Dict[str, Type[BaseRelationshipHandler]]:
        """Discover relationship handlers for a language using self-describing handlers."""
        handlers = {}

        # Get language definition to see which generic handlers to use
        language_definition = self._get_language_definition(language)
        generic_handlers_to_use = getattr(language_definition, 'uses_generic_handlers', [])

        # Discover generic handlers
        self._discover_handlers("common", handlers, filter_by=generic_handlers_to_use)

        # Discover language-specific handlers (these override generic ones)
        self._discover_handlers(language, handlers)

        return handlers

    def _discover_handlers(self, language_or_common: str, handlers: dict, filter_by: Optional[List[str]] = None):
        """Discover handlers from the filesystem and filter by language opt-in."""
        package_path = Path(__file__).parent / "relationship_handlers" / language_or_common

        if not package_path.is_dir():
            return

        package_name = f"src.code_index_mcp.indexing.relationship_handlers.{language_or_common}"

        for _, module_name, _ in pkgutil.iter_modules([str(package_path)]):
            try:
                module = importlib.import_module(f".{module_name}", package=package_name)
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if (isinstance(attribute, type) and
                        issubclass(attribute, BaseRelationshipHandler) and
                        attribute is not BaseRelationshipHandler):

                        # If filter provided, only include handlers the language opts into
                        if filter_by and attribute.__name__ not in filter_by:
                            continue

                        handler_key = attribute.relationship_type
                        if handler_key:
                            handlers[handler_key] = attribute
            except ImportError as e:
                self.logger.mustLog("Orchestrator", f"Failed to import handler module {module_name}: {e}")
                raise e

    def _get_language_capabilities(self, language: str) -> Dict[str, List[str]]:
        """Discover language capabilities by inspecting available handlers."""
        handlers = self._get_relationship_handlers(language)

        symbol_types = set()
        relationship_types = set()

        for handler_class in handlers.values():
            # Collect required symbol types from handlers
            if hasattr(handler_class, 'required_symbol_types'):
                symbol_types.update(handler_class.required_symbol_types)

            # Collect relationship types from handlers
            if hasattr(handler_class, 'relationship_type'):
                relationship_types.add(handler_class.relationship_type)

        return {
            'symbol_types': sorted(list(symbol_types)),
            'relationship_types': sorted(list(relationship_types))
        }

    def _sort_handlers_by_dependencies(self, handlers: Dict[str, Type[BaseRelationshipHandler]]) -> Dict[str, Type[BaseRelationshipHandler]]:
        """Sort handlers so dependencies are resolved first."""
        # Simple topological sort based on phase_dependencies
        sorted_handlers = {}
        remaining = dict(handlers)

        while remaining:
            # Find handlers with no unresolved dependencies
            ready_handlers = {}
            for rel_type, handler_class in remaining.items():
                deps = getattr(handler_class, 'phase_dependencies', [])
                if all(dep in sorted_handlers for dep in deps):
                    ready_handlers[rel_type] = handler_class

            if not ready_handlers:
                raise ValueError(f"Circular dependency detected in handlers: {list(remaining.keys())}")

            # Add ready handlers to sorted list
            sorted_handlers.update(ready_handlers)
            for rel_type in ready_handlers:
                del remaining[rel_type]

        return sorted_handlers

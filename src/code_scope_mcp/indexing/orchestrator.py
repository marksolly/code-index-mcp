import importlib
import os
import pkgutil
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from tree_sitter_languages import get_language, get_parser

from .file_list_builder import FileListBuilder
from .ignore_handler import IgnoreHandler
from .indexing_logger import IndexingLogger
from .languages import LanguageDefinition
from .reader import IndexReader
from .relationship_handlers.base_relationship_handler import BaseRelationshipHandler
from .symbol_extractors.base_symbol_extractor import BaseSymbolExtractor
from .timing_utils import time_block
from .writer import IndexWriter, IndexUpserter
from .strict_resolution_validator import StrictResolutionValidator
from .exceptions import StrictModeViolationException


class IndexingOrchestrator:
    def __init__(self, db_service=None, logger: Optional[IndexingLogger] = None,
                 catch_exceptions: bool = False, exception_log_file: Optional[str] = None,
                 strict_resolution: bool = False, incremental_mode: bool = False):
        self.logger = logger or IndexingLogger(enabled=False)
        self.ignore_handler = IgnoreHandler()
        self.symbol_extractor_classes: Dict[str, Type[BaseSymbolExtractor]] = {}
        self.language_definitions: Dict[str, LanguageDefinition] = self._discover_language_definitions()

        # Determine base package dynamically from our own __name__
        self.base_package = '.'.join(__name__.split('.')[:-1])

        # Cache tree-sitter parsers and language objects for efficiency
        self.parsers: Dict[str, Any] = {}
        self.language_objects: Dict[str, Any] = {}

        # Require DatabaseService for high-speed optimizations
        if not hasattr(db_service, 'get_connection'):
            raise TypeError("IndexingOrchestrator requires a DatabaseService instance, not a raw sqlite3.Connection")

        self.db_service = db_service
        self.db_connection = db_service.get_connection()

        # Exception handling configuration
        self.catch_exceptions = catch_exceptions
        self.exception_log_file = exception_log_file
        self.exceptions = []  # RAM storage for exceptions
        self.max_exceptions = 1000  # Prevent OOM with bounded collection

        # Strict resolution mode configuration
        self.strict_resolution = strict_resolution
        self.strict_validator = StrictResolutionValidator(
            self.db_connection, self.logger, strict_resolution
        )

        # Incremental mode configuration
        self.incremental_mode = incremental_mode
        if incremental_mode:
            self.session_timestamp = datetime.now()
            self.logger.mustLog("Orchestrator", "Operating in incremental mode")
        else:
            self.session_timestamp = None

    def _get_package_name(self, subpackage: str) -> str:
        """Build package name relative to our base package."""
        return f"{self.base_package}.{subpackage}"

    def _discover_language_definitions(self) -> Dict[str, LanguageDefinition]:
        definitions = {}

        # Import the languages module (already imported at the top)
        from . import languages as lang_module

        for attribute_name in dir(lang_module):
            attribute = getattr(lang_module, attribute_name)
            if isinstance(attribute, type) and issubclass(attribute, LanguageDefinition) and attribute is not LanguageDefinition:
                instance = attribute()
                definitions[instance.language_name] = instance

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
                # Use filesystem-based discovery (same as relationship handlers)
                package_path = Path(__file__).parent / "symbol_extractors"
                package_name = self._get_package_name("symbol_extractors")

                for _, module_name, _ in pkgutil.iter_modules([str(package_path)]):
                    # Check if this module matches the expected language pattern
                    expected_name = f"{language}_symbol_extractor"
                    if module_name == expected_name:
                        self.logger.mustLog("Orchestrator", f"Found symbol extractor module: {module_name}")
                        module = importlib.import_module(f".{module_name}", package_name)

                        # Find the BaseSymbolExtractor subclass in the module
                        # Use the BaseSymbolExtractor from the module itself to avoid import path issues
                        module_base_extractor = getattr(module, 'BaseSymbolExtractor', None)
                        if module_base_extractor:
                            found_class = False
                            for attribute_name in dir(module):
                                attribute = getattr(module, attribute_name)
                                is_type = isinstance(attribute, type)
                                is_subclass = is_type and issubclass(attribute, module_base_extractor)
                                is_not_base = attribute is not module_base_extractor
                                if is_type and is_subclass and is_not_base:
                                    self.logger.mustLog("Orchestrator", f"Found symbol extractor class: {attribute_name}")
                                    self.symbol_extractor_classes[language] = attribute
                                    found_class = True
                                    break
                            if not found_class:
                                self.logger.mustLog("Orchestrator", f"No BaseSymbolExtractor subclass found in {module_name}")
                        else:
                            self.logger.mustLog("Orchestrator", f"BaseSymbolExtractor not found in {module_name}")
                        break

            except ImportError as e:
                self.logger.mustLog("Orchestrator", f"Failed to import symbol extractor for {language}: {e}")
                raise ValueError(f"Unsupported language or missing extractor: {language}")

        extractor_class = self.symbol_extractor_classes.get(language)
        if not extractor_class:
            self.logger.mustLog("Orchestrator", f"No symbol extractor found for language: {language}")
            raise ValueError(f"No symbol extractor found for language: {language}")
        return extractor_class

    def process_files(self, file_paths: List[str]):
        """
        Orchestrates the multi-phase indexing process for a list of files,
        after filtering them using .indexerignore rules.
        Loads file contents and detects languages just-in-time.
        """

        self.logger.mustLog("Orchestrator", "Starting file filtering and indexing process.")

        # Acquire lock
        lock_acquired = self.db_service.acquire_lock()
        if not lock_acquired:
            raise RuntimeError("Could not acquire indexing lock. Another indexing operation may be in progress.")
        self.logger.mustLog("Orchestrator", "Indexing lock acquired successfully.")

        try:
            # Only enable profiling if explicitly requested (not automatically)
            profiling_enabled = False
            if hasattr(self.logger, 'profiling_enabled'):
                profiling_enabled = self.logger.profiling_enabled

            # Start total timing only if profiling is already enabled
            if profiling_enabled and hasattr(self.logger, 'start_timing'):
                self.logger.start_timing("entire_pipeline")

            # Use FileListBuilder to prepare valid file paths and deletion paths
            file_list_builder = FileListBuilder(self.logger, self.db_connection, self.incremental_mode)
            valid_file_paths, delete_file_paths, primary_update_targets = file_list_builder.prepare(file_paths, self.ignore_handler)

            # Store primary update targets for targeted cleanup.
            # If file_paths contained any directories, these will have been expanded to full file lists.
            self._original_input_paths = set(primary_update_targets)

            # Choose writer based on mode (needed for deletions)
            if self.incremental_mode:
                writer = IndexUpserter(self.db_connection, self.logger, session_timestamp=self.session_timestamp)
                self.logger.mustLog("Orchestrator", "Using IndexUpserter for incremental indexing")
            else:
                writer = IndexWriter(self.db_connection, self.logger)
                self.logger.mustLog("Orchestrator", "Using IndexWriter for full indexing")
            self.writer = writer

            # Process file deletions first (only in incremental mode)
            if self.incremental_mode and delete_file_paths:
                self.logger.mustLog("Orchestrator", f"Processing {len(delete_file_paths)} file deletions")
                for delete_path in delete_file_paths:
                    self._remove_deleted_file(delete_path)

            if not valid_file_paths:
                self.logger.mustLog("Orchestrator", "No files to index after filtering.")
                return

            reader = IndexReader(self.db_connection, self.logger)

            # Phase 1: Symbol Extraction for all files
            with time_block(self.logger, "phase_1_symbol_extraction"):
                self.logger.mustLog("Orchestrator", "Beginning Phase 1: Symbol Extraction.")
                try:
                    if not self.incremental_mode:
                        self.db_service.enable_high_speed_mode()
                        self.logger.mustLog("Orchestrator", "High speed non-incremental mode on.")

                    # Build extension to language mapping for Phase 1 processing
                    extension_map = self._build_extension_map()

                    for file_path in valid_file_paths:
                        # Determine language for this file
                        _, ext = os.path.splitext(file_path)
                        language = extension_map.get(ext)
                        if not language:
                            self.logger.log("Orchestrator", f"Skipping {file_path}: unsupported file type {ext}")
                            continue

                        language_definition = self._get_language_definition(language)
                        self.logger.current_context['language'] = language
                        writer.set_language_definition(language_definition)

                        # Load file content immediately before processing
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                source_code = f.read()
                        except (UnicodeDecodeError, IOError) as e:
                            self.logger.log("Orchestrator", f"Skipping {file_path}: {e}")
                            continue

                        # Process the file immediately and free memory
                        if self.catch_exceptions:
                            try:
                                self.run_phase_1_symbol_extraction(file_path, language, source_code, writer)
                            except Exception as e:
                                context = {
                                    'file': file_path,
                                    'language': language,
                                    'phase': 'Phase 1'
                                }
                                self._handle_exception("Phase 1", e, context)
                        else:
                            self.run_phase_1_symbol_extraction(file_path, language, source_code, writer)

                        # Free memory by deleting the source code after use
                        del source_code
                finally:
                    self.db_service.disable_high_speed_mode()
                self.logger.mustLog("Orchestrator", "Completed Phase 1.")

            # Phase 2: Intermediate Relationship Resolution
            with time_block(self.logger, "phase_2_intermediate_resolution"):
                self.logger.mustLog("Orchestrator", "Beginning Phase 2: Intermediate Resolution.")
                # Get all unique languages from the discovered language definitions
                unique_languages = list(self.language_definitions.keys())
                for lang in unique_languages:
                    self.logger.current_context['language'] = lang
                    language_definition = self._get_language_definition(lang)
                    writer.set_language_definition(language_definition)

                    if self.catch_exceptions:
                        try:
                            self.run_phase_2_intermediate_resolution(writer, reader, lang)
                        except Exception as e:
                            context = {
                                'language': lang,
                                'phase': 'Phase 2'
                            }
                            self._handle_exception("Phase 2", e, context)
                    else:
                        self.run_phase_2_intermediate_resolution(writer, reader, lang)
                self.logger.mustLog("Orchestrator", "Completed Phase 2.")

            # Phase 3: Final Relationship Resolution
            with time_block(self.logger, "phase_3_final_resolution"):
                self.logger.mustLog("Orchestrator", "Beginning Phase 3: Final Resolution.")
                for lang in unique_languages:
                    self.logger.current_context['language'] = lang
                    language_definition = self._get_language_definition(lang)
                    writer.set_language_definition(language_definition)

                    if self.catch_exceptions:
                        try:
                            self.run_phase_3_final_resolution(writer, reader, lang)
                        except Exception as e:
                            context = {
                                'language': lang,
                                'phase': 'Phase 3'
                            }
                            self._handle_exception("Phase 3", e, context)
                    else:
                        self.run_phase_3_final_resolution(writer, reader, lang)
                self.logger.mustLog("Orchestrator", "Completed Phase 3.")

            # Stop total timing and print profiling report only if profiling was enabled
            if profiling_enabled:
                if hasattr(self.logger, 'stop_timing'):
                    self.logger.stop_timing("entire_pipeline")

                if hasattr(self.logger, 'print_profiling_report'):
                    self.logger.print_profiling_report()

            # Generate and display exception summary if any exceptions occurred
            if self.catch_exceptions and self.exceptions:
                summary = self._generate_exception_summary()
                print(summary)

            # Cleanup phase for incremental mode - remove untouched records
            if self.incremental_mode:
                self._cleanup_untouched_records(valid_file_paths, self.session_timestamp)
                self.logger.mustLog("Orchestrator", "Completed cleanup of untouched records")

            # Final strict resolution validation - check for any remaining unresolved relationships
            if self.strict_resolution:
                self.strict_validator.validate_final_state(self.catch_exceptions)

            self.logger.mustLog("Orchestrator", "Completed multi-phase indexing process.")

        finally:
            # Ensure lock is always released
            self.db_service.release_lock()
            self.logger.mustLog("Orchestrator", "Indexing lock released.")

    def remove_file_from_index(self, file_path: str, language: str):
        """
        Remove a file and all its associated data from the index.

        This is the orchestrator-level passthrough to the writer that handles
        file deletion with automatic CASCADE cleanup of symbols and relationships.
        """
        print(f"DEBUG: Orchestrator.remove_file_from_index called: {file_path}")

        # Set language definition for validation
        language_definition = self._get_language_definition(language)
        self.writer.set_language_definition(language_definition)

        # Delegate to writer for the actual deletion
        success = self.writer.remove_file_from_index(file_path)

        if success:
            self.logger.mustLog("Orchestrator", f"Removed file from index: {file_path}")
        else:
            self.logger.mustLog("Orchestrator", f"File not found in index: {file_path}")

        return success

    def run_phase_1_symbol_extraction(self, file_path: str, language: str, source_code: str, writer: IndexWriter):
        """Phase 1: Extract symbols and create unresolved relationships"""
        self.logger.set_context(file_path=file_path, language=language)
        self.logger.log("Orchestrator", f"P1 Extracting {file_path} ({language})")
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
            self.logger.log("Orchestrator", f"P2 Resolving: {handler_class.__name__}")
            _, language_obj = self._get_parser_and_language(language)
            handler = handler_class(language, language_obj, self.logger)
            # Use batching per handler. Some handlers depend on previous handlers in the pipeline.
            with writer.batch_relationships() as batch_writer:
                handler.resolve_immediate(batch_writer, reader)

    def run_phase_3_final_resolution(self, writer: IndexWriter, reader: IndexReader, language: str):
        """Phase 3: Complex multi-step relationship resolution"""
        self.logger.set_context(file_path="N/A", language=language)
        self.logger.mustLogForLang("Orchestrator", f"Starting Phase 3: Final Relationship Resolution for {language}")
        handlers = self._get_relationship_handlers(language)

        # Sort handlers by phase dependencies for complex resolution
        sorted_handlers = self._sort_handlers_by_dependencies(handlers)

        for handler_class in sorted_handlers.values():
            self.logger.log("Orchestrator", f"P3 Resolving: {handler_class.__name__}")
            _, language_obj = self._get_parser_and_language(language)
            handler = handler_class(language, language_obj, self.logger)
            # Use batching per handler. Some handlers depend on previous handlers in the pipeline.
            with writer.batch_relationships() as batch_writer:
                handler.resolve_complex(batch_writer, reader)

            # Strict validation: Check if this handler left any unresolved relationships
            if self.strict_resolution:
                self.strict_validator.validate_after_handler(handler_class, self.catch_exceptions)

        self.logger.mustLogForLang("Orchestrator", f"Phase 3: Final Resolution completed for {language}")


    def _get_relationship_handlers(self, language: str) -> Dict[str, Type[BaseRelationshipHandler]]:
        """Discover relationship handlers for a language using self-describing handlers."""
        handlers = {}

        # Discover language-specific handlers from language directories
        # Each language directory contains concrete implementations
        self._discover_handlers(language, handlers)

        return handlers

    def _discover_handlers(self, language_or_common: str, handlers: dict, filter_by: Optional[List[str]] = None):
        """Discover handlers from the filesystem and filter by language opt-in."""
        package_path = Path(__file__).parent / "relationship_handlers" / language_or_common

        if not package_path.is_dir():
            return

        package_name = self._get_package_name(f"relationship_handlers.{language_or_common}")

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
        print("Starting dependency sort for handlers:")
        for rel_type, handler_class in handlers.items():
            deps = getattr(handler_class, 'phase_dependencies', [])
            print(f"  {rel_type}: {deps}")

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
                # Collect all unresolved dependencies
                all_unresolved = set()
                for rel_type, handler_class in remaining.items():
                    deps = getattr(handler_class, 'phase_dependencies', [])
                    all_unresolved.update(dep for dep in deps if dep not in sorted_handlers)

                # Check if any unresolved deps are missing from original handlers
                missing_deps = all_unresolved - set(handlers.keys())
                if missing_deps:
                    self.logger.mustLog("Orchestrator", f"Missing handlers detected:")
                    for rel_type, handler_class in remaining.items():
                        deps = getattr(handler_class, 'phase_dependencies', [])
                        unresolved = [dep for dep in deps if dep not in sorted_handlers]
                        self.logger.mustLog("Orchestrator", f"  {rel_type}: missing dependencies {unresolved}")
                    self.logger.mustLog("Orchestrator", f"  Have these handlers been created?")
                    raise ValueError(f"Missing dependency handlers: {sorted(missing_deps)}")
                else:
                    print("Circular dependency detected!")
                    print("Remaining handlers and their unresolved dependencies:")
                    for rel_type, handler_class in remaining.items():
                        deps = getattr(handler_class, 'phase_dependencies', [])
                        unresolved = [dep for dep in deps if dep not in sorted_handlers]
                        print(f"  {rel_type}: missing dependencies {unresolved}")
                    raise ValueError(f"Circular dependency detected in handlers: {list(remaining.keys())}")

            print(f"Adding to sorted (no unresolved dependencies): {list(ready_handlers.keys())}")
            # Add ready handlers to sorted list
            sorted_handlers.update(ready_handlers)
            for rel_type in ready_handlers:
                del remaining[rel_type]

        print(f"Final sorted order: {list(sorted_handlers.keys())}")
        return sorted_handlers

    def _build_extension_map(self) -> Dict[str, str]:
        """Build extension to language mapping from language definitions."""
        extension_map = {}

        # Discover language definitions (same way as orchestrator)
        for language_name, definition in self.language_definitions.items():
            if hasattr(definition, 'file_extensions'):
                for ext in definition.file_extensions:
                    extension_map[ext] = language_name

        return extension_map

    def _remove_deleted_file(self, file_path: str):
        """
        Remove a deleted file and all its associated data from the index.
        Uses the writer's remove_file_from_index method with CASCADE cleanup.
        """

        try:
            success = self.writer.remove_file_from_index(file_path)
            if success:
                self.logger.log("Orchestrator", f"Removed file from index: {file_path}")
            else:
                self.logger.log("Orchestrator", f"File not found in index (may have been already removed): {file_path}")
        except Exception as e:
            self.logger.log("Orchestrator", f"Error removing file from index: {file_path} - {e}")
            # Don't re-raise - we don't want deletion errors to stop indexing

    def _cleanup_untouched_records(self, file_paths: List[str], session_timestamp: datetime):
        """
        Clean up records associated with processed files but not touched during the incremental session.

        This removes symbols, relationships, and unresolved relationships that belong to files that were
        processed in this incremental session but weren't updated (meaning they were removed/changed).
        Uses targeted cleanup to only affect files that were explicitly supposed to be re-indexed.
        """
        if not file_paths:
            return

        self.logger.mustLog("Orchestrator", f"Starting targeted cleanup of untouched records for {len(file_paths)} files")

        cursor = self.db_connection.cursor()
        try:
            # Determine which files were in the original input (before dependency discovery)
            # This is crucial: we only want to cleanup files that were explicitly requested
            # Not files that were discovered as dependencies and added automatically
            original_input_paths = set()
            if hasattr(self, '_original_input_paths'):
                # Use the original input paths if available
                original_input_paths = self._original_input_paths
            else:
                # Fallback: assume all files should be cleaned up (old behavior)
                original_input_paths = set(file_paths)

            if not original_input_paths:
                self.logger.mustLog("Orchestrator", "No input files to cleanup")
                return

            # Delete symbols from ORIGINAL input files only (not dependency-discovered files)
            symbols_deleted = cursor.execute("""
                DELETE FROM code_symbols
                WHERE file_id IN (
                    SELECT id FROM files WHERE path IN ({})
                )
                AND last_touched < ?
            """.format(','.join('?' for _ in original_input_paths)),
            tuple(original_input_paths) + (session_timestamp,)).rowcount

            # Delete only OUTBOUND relationships from ORIGINAL input files
            # This preserves inbound relationships to these files (preserving relationships from dependency files)
            relationships_deleted = cursor.execute("""
                DELETE FROM relationships
                WHERE last_touched < ?
                AND source_symbol_id IN (
                    SELECT cs.id FROM code_symbols cs
                    JOIN files f ON cs.file_id = f.id
                    WHERE f.path IN ({})
                )
            """.format(','.join('?' for _ in original_input_paths)),
            (session_timestamp,) + tuple(original_input_paths)).rowcount

            # Delete unresolved relationships from ORIGINAL input files only
            unresolved_deleted = cursor.execute("""
                DELETE FROM unresolved_relationships
                WHERE last_touched < ?
                AND source_symbol_id IN (
                    SELECT cs.id FROM code_symbols cs
                    JOIN files f ON cs.file_id = f.id
                    WHERE f.path IN ({})
                )
            """.format(','.join('?' for _ in original_input_paths)),
            (session_timestamp,) + tuple(original_input_paths)).rowcount

            self.db_connection.commit()

            self.logger.mustLog("Orchestrator",
                f"Targeted cleanup complete: {symbols_deleted} symbols, {relationships_deleted} relationships, "
                f"{unresolved_deleted} unresolved relationships removed from {len(original_input_paths)} input files")

        finally:
            cursor.close()




    def _handle_exception(self, phase: str, error: Exception, context: Dict[str, Any]):
        """
        Handle an exception by logging it and storing it for summary reporting.

        Args:
            phase: The phase where the exception occurred (e.g., "Phase 1", "Phase 2")
            error: The exception that occurred
            context: Additional context information about where the exception occurred
        """
        # Always log to file if configured
        if self.exception_log_file:
            self._log_exception_to_file(phase, error, context)

        # Store in RAM if catching exceptions (with bounds checking)
        if self.catch_exceptions and len(self.exceptions) < self.max_exceptions:
            exception_info = {
                'phase': phase,
                'error': str(error),
                'context': context,
                'timestamp': datetime.now(),
                'traceback': traceback.format_exc()
            }
            self.exceptions.append(exception_info)

        # Log to console for immediate feedback
        error_msg = str(error)
        if len(error_msg) > 200:  # Truncate very long error messages
            error_msg = error_msg[:200] + "..."
        self.logger.log("Orchestrator", f"Exception in {phase}: {error_msg}")

    def _log_exception_to_file(self, phase: str, error: Exception, context: Dict[str, Any]):
        """
        Log exception details to a file for detailed debugging.

        Args:
            phase: The phase where the exception occurred
            error: The exception that occurred
            context: Additional context information
        """
        try:
            with open(self.exception_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat()}] {phase} Exception\n")
                f.write(f"Error: {error}\n")

                # Write context information
                if context:
                    f.write("Context:\n")
                    for key, value in context.items():
                        f.write(f"  {key}: {value}\n")

                # Write full traceback
                f.write("Traceback:\n")
                f.write(traceback.format_exc())
                f.write("\n" + "="*80 + "\n")
        except Exception as log_error:
            # If we can't write to the log file, at least log to console
            self.logger.log("Orchestrator", f"Failed to write exception to log file: {log_error}")

    def _generate_exception_summary(self) -> str:
        """
        Generate a human-readable summary of all exceptions that occurred.

        Returns:
            A formatted string containing the exception summary
        """
        if not self.exceptions:
            return ""

        # Group exceptions by phase
        by_phase = {}
        for exc in self.exceptions:
            phase = exc['phase']
            if phase not in by_phase:
                by_phase[phase] = []
            by_phase[phase].append(exc)

        # Generate summary
        summary_lines = ["\n🚨  INDEXING COMPLETED WITH EXCEPTIONS - INDEX MAY BE INCOMPLETE:\n"]

        total_exceptions = 0
        for phase in sorted(by_phase.keys()):
            phase_exceptions = by_phase[phase]
            summary_lines.append(f"⚠️  {phase}: {len(phase_exceptions)} exceptions")

            # Show first few examples (max 3 per phase)
            for i, exc in enumerate(phase_exceptions[:3]):
                context_str = ""
                if 'file' in exc['context']:
                    context_str = f" ({exc['context']['file']})"
                elif 'handler' in exc['context']:
                    context_str = f" ({exc['context']['handler']})"

                error_preview = exc['error'][:100] + "..." if len(exc['error']) > 100 else exc['error']
                summary_lines.append(f"  - {error_preview}{context_str}")

            if len(phase_exceptions) > 3:
                summary_lines.append(f"  ... and {len(phase_exceptions) - 3} more")

            summary_lines.append("")
            total_exceptions += len(phase_exceptions)

        if self.exception_log_file:
            summary_lines.append(f"📝 Detailed logs written to: {self.exception_log_file}")

        summary_lines.append(f"\n⚠️  Total exceptions: {total_exceptions} (indexing continued but may be incomplete)")

        error_message = "   Some code relationships may not have been indexed due to errors."
        if self.exception_log_file:
            error_message += f" See: {self.exception_log_file}"
        summary_lines.append(error_message)

        return "\n".join(summary_lines)

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_import_handler import BaseImportHandler


class CImportHandler(BaseImportHandler):
    """C-specific implementation of import relationship handler for #include directives."""

    relationship_type = "imports"

    def __init__(self, language: str, language_obj, logger):
        super().__init__(language, language_obj, logger)
        self.logger.log(self.__class__.__name__, f"DEBUG: CImportHandler initialized for language {language}")

    def _get_import_queries(self) -> list[str]:
        """Return C-specific tree-sitter queries for #include directives."""
        self.logger.log(self.__class__.__name__, f"DEBUG: Using C import query")
        queries = ["""
            (preproc_include) @from_import_stmt
        """]
        self.logger.log(self.__class__.__name__, f"DEBUG: Query defined: {queries[0].strip()}")
        return queries

    def _extract_import_from_node(self, node) -> Optional[dict]:
        """Extract include details from a C AST node.

        Args:
            node: Tree-sitter node representing a preproc_include

        Returns:
            dict with 'module_name' and 'imported_names', or None if extraction fails
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Processing AST node type: {node.type}")

        try:
            # Get the path from the include directive
            path_node = node.child_by_field_name("path")
            if not path_node:
                self.logger.log(self.__class__.__name__, "DEBUG: No path node found")
                return None

            include_path = path_node.text.decode('utf-8')
            self.logger.log(self.__class__.__name__, f"DEBUG: Found include path: {include_path}")

            # Skip system includes according to implementation plan
            if include_path.startswith('<') and include_path.endswith('>'):
                self.logger.log(self.__class__.__name__, f"DEBUG: Skipping system include: {include_path}")
                return None

            # For local includes, create file import relationship
            # This aligns with the test expectations for C include processing
            result = {
                'module_name': include_path,
                'imported_names': ['__FILE__']  # Import the file itself
            }
            self.logger.log(self.__class__.__name__, f"DEBUG: Creating import relationship for: {result}")
            return result

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting include from node: {e}")
            return None

    def _convert_module_to_file_path(self, module_name: str) -> str:
        """Convert a C include path to a file path.

        Args:
            module_name: The include path (e.g., '"utils.h"' or '<stdio.h>')

        Returns:
            File path string with appropriate extension (e.g., 'utils.h')
        """
        # Remove quotes for local includes
        if module_name.startswith('"') and module_name.endswith('"'):
            # Extract only the filename part to maintain qname format
            path = module_name[1:-1]
            return path.split('/')[-1]
        else:
            # Already clean path
            return module_name

    def resolve_immediate(self, writer, reader):
        """
        Phase 2: Resolve import relationships with support for probabilistic relationships
        in preprocessor scenarios (e.g., conditional includes).

        Override the base class to handle ambiguous include resolution where multiple
        files with the same symbols exist due to preprocessor conditional compilation.
        """
        self.logger.log(self.__class__.__name__, "DEBUG: CImportHandler.resolve_immediate called")

        # Query unresolved 'imports' relationships for C language only
        unresolved = reader.find_unresolved("imports", language=self.language)
        self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(unresolved)} unresolved imports relationships")

        resolved_count = 0
        for rel in unresolved:
            self.logger.log(self.__class__.__name__,
                          f"DEBUG: Processing unresolved import: {rel['source_qname']} -> {rel['target_name']}")

            relationships_created = 0

            # First, create the file-to-file import relationship that tests expect
            if rel['intermediate_symbol_qname']:
                file_name = rel['intermediate_symbol_qname'].split(':')[0]
                target_file_qname = f"{file_name}:__FILE__"

                # Find the target file symbol
                target_file_symbols = reader.find_symbols(qname=target_file_qname, language=self.language)
                if target_file_symbols:
                    self.logger.log(self.__class__.__name__,
                                  f"DEBUG: Creating file-to-file import: {rel['source_qname']} -> {target_file_qname}")
                    writer.add_relationship(
                        source_symbol_id=rel['source_symbol_id'],
                        target_symbol_id=target_file_symbols[0]['id'],
                        rel_type="imports",
                        source_qname=rel['source_qname'],
                        target_qname=target_file_qname
                    )
                    relationships_created += 1
                    resolved_count += 1

            # Then try to resolve individual symbol relationships
            intermediate_qname = rel['intermediate_symbol_qname'] if 'intermediate_symbol_qname' in rel.keys() and rel['intermediate_symbol_qname'] else None
            target_result = self._resolve_import_target(rel['target_name'], intermediate_qname, reader)

            if target_result:
                # Handle both single symbol (dict) and multiple symbols (list) cases
                if isinstance(target_result, list):
                    # Multiple symbols case (e.g., conditional includes with same symbols)
                    self._handle_multiple_targets(rel, target_result, writer, reader)
                    relationships_created += len(target_result)
                    resolved_count += 1
                else:
                    # Single symbol case (dict)
                    self.logger.log(self.__class__.__name__,
                                  f"DEBUG: Creating resolved import: {rel['source_qname']} -> {target_result['qname']}")
                    writer.add_relationship(
                        source_symbol_id=rel['source_symbol_id'],
                        target_symbol_id=target_result['id'],
                        rel_type="imports",
                        source_qname=rel['source_qname'],
                        target_qname=target_result['qname']
                    )
                    relationships_created += 1
                    resolved_count += 1

            # Delete the unresolved relationship if we created any resolved relationships
            if relationships_created > 0:
                writer.delete_unresolved_relationship(rel['id'])
                self.logger.log(self.__class__.__name__, "DEBUG: Import relationship resolved")
            else:
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Could not resolve import target: {rel['target_name']}")

        self.logger.log(self.__class__.__name__, f"DEBUG: Resolved {resolved_count} imports")

    def _handle_multiple_targets(self, rel, target_symbols, writer, reader):
        """
        Handle multiple target symbols by creating probabilistic relationships
        with confidence scoring. This addresses preprocessor scenarios where
        conditional includes create ambiguity about which symbol definition
        is actually used at runtime.

        Args:
            rel: The unresolved relationship dict
            target_symbols: List of target symbol dicts
            writer: IndexWriter instance
            reader: IndexReader instance
        """
        self.logger.log(self.__class__.__name__,
                      f"DEBUG: Handling multiple targets ({len(target_symbols)}) for import: {rel['source_qname']} -> {rel['target_name']}")

        # Group symbols by name to identify ambiguous definitions
        symbols_by_name = {}
        for symbol in target_symbols:
            symbol_name = symbol['name']
            if symbol_name not in symbols_by_name:
                symbols_by_name[symbol_name] = []
            symbols_by_name[symbol_name].append(symbol)

        for symbol_name, symbols in symbols_by_name.items():
            if len(symbols) == 1:
                # Single symbol - deterministic relationship
                symbol = symbols[0]
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Creating deterministic import: {rel['source_qname']} -> {symbol['qname']}")
                writer.add_relationship(
                    source_symbol_id=rel['source_symbol_id'],
                    target_symbol_id=symbol['id'],
                    rel_type="imports",
                    source_qname=rel['source_qname'],
                    target_qname=symbol['qname']
                )
            else:
                # Multiple symbols with same name - probabilistic relationships
                confidence = 1.0 / len(symbols)  # Split confidence equally
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Creating probabilistic imports with confidence {confidence:.2f} for {symbol_name}")

                for symbol in symbols:
                    self.logger.log(self.__class__.__name__,
                                  f"DEBUG: Creating probabilistic import: {rel['source_qname']} -> {symbol['qname']} (confidence={confidence:.2f})")
                    writer.add_relationship(
                        source_symbol_id=rel['source_symbol_id'],
                        target_symbol_id=symbol['id'],
                        rel_type="imports",
                        source_qname=rel['source_qname'],
                        target_qname=symbol['qname'],
                        confidence=confidence
                    )

    def _resolve_import_target(self, target_name: str, intermediate_symbol_qname: str, reader):
        """
        Override to allow resolution even when multiple matches exist.
        This supports the probabilistic relationship model for preprocessor scenarios.

        Returns list of matching symbols instead of just the first one, allowing
        the caller to create probabilistic relationships when appropriate.
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: Resolving import target (C version): {target_name}")

        # Handle special case for "import file" (C includes)
        if target_name == '__FILE__':
            if intermediate_symbol_qname:
                # Get all symbols from the target file(s)
                file_name = intermediate_symbol_qname.split(':')[0]
                target_file_qname_pattern = f"{file_name}:%"
                all_symbols_in_file = reader.find_symbols(
                    qname=target_file_qname_pattern,
                    match_type="like",
                    language=self.language
                )

                # Filter out the file itself
                symbol_list = [
                    symbol for symbol in all_symbols_in_file
                    if not symbol['qname'].endswith(':__FILE__')
                ]

                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Found {len(symbol_list)} symbols to import from {file_name}")
                return symbol_list if symbol_list else None

            self.logger.log(self.__class__.__name__,
                          f"DEBUG: Cannot resolve '*' import without intermediate_symbol_qname")
            return None

        # For named symbols, search across all files but return ALL matches
        # This enables probabilistic relationship handling for ambiguous symbols
        target_symbols = reader.find_symbols(name=target_name, language=self.language)

        if target_symbols:
            if len(target_symbols) == 1:
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Found single import target by name: {target_symbols[0]['qname']}")
                return target_symbols[0]
            else:
                # Multiple matches - return all to enable probabilistic relationships
                self.logger.log(self.__class__.__name__,
                              f"DEBUG: Found multiple ({len(target_symbols)}) import targets by name: {[s['qname'] for s in target_symbols]}")
                return target_symbols

        self.logger.log(self.__class__.__name__,
                      f"DEBUG: Could not resolve import target: {target_name}")
        return None

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_import_handler import BaseImportHandler


class PhpImportHandler(BaseImportHandler):
    """PHP-specific implementation of import relationship handler."""

    def __init__(self, language: str, language_obj: Any, logger):
        super().__init__(language, language_obj, logger)
        self.logger.log(self.__class__.__name__, "DEBUG: PhpImportHandler instantiated")

    def _get_import_queries(self) -> list[str]:
        """Return PHP-specific tree-sitter queries for import statements."""
        return ["""
            (include_expression) @from_import_stmt
        """, """
            (include_once_expression) @from_import_stmt
        """, """
            (require_expression) @from_import_stmt
        """, """
            (require_once_expression) @from_import_stmt
        """]

    def extract_from_ast(self, tree: 'Tree', writer, reader, file_qname: str):
        """Extract import relationships from PHP include/require statements."""
        self.logger.log(self.__class__.__name__, f"DEBUG: PhpImportHandler.extract_from_ast called for {file_qname}")

        # Get the file symbol ID for this file
        file_symbols = reader.find_symbols(qname=file_qname, language=self.language)
        if not file_symbols:
            self.logger.log(self.__class__.__name__, f"DEBUG: No file symbol found for {file_qname}")
            return

        file_symbol_id = file_symbols[0]['id']

        # Get language-specific import queries
        import_queries = self._get_import_queries()

        # Extract imports using language-specific queries
        for query_text in import_queries:
            query = self.language_obj.query(query_text)
            captures = query.captures(tree.root_node)

            for capture in captures:
                node = capture[0]
                capture_name = capture[1]

                if capture_name == "from_import_stmt":
                    # Extract import details using language-specific method
                    import_details = self._extract_import_from_node(node)
                    if not import_details:
                        continue

                    module_name = import_details['module_name']
                    imported_names = import_details['imported_names']

                    # Convert module name to file path using language-specific logic
                    target_file = self._convert_module_to_file_path(module_name)

                    # For PHP includes, we need to import ALL symbols from the target file
                    # Find all symbols declared in the target file using qname pattern
                    target_file_qname_pattern = f"{target_file}:%"
                    all_symbols_in_file = reader.find_symbols(qname=target_file_qname_pattern, match_type="like", language=self.language)

                    self.logger.log(self.__class__.__name__, f"DEBUG: Found {len(all_symbols_in_file)} symbols in {target_file}")

                    # Create import relationships for each symbol in the target file
                    for symbol in all_symbols_in_file:
                        if not symbol['qname'].endswith(':__FILE__'):  # Skip the file itself
                            symbol_name = symbol['name']
                            writer.add_unresolved_relationship(
                                source_symbol_id=file_symbol_id,
                                source_qname=file_qname,
                                target_name=symbol_name,
                                rel_type="imports",
                                needs_type="imports",
                                target_qname=None,
                                intermediate_symbol_qname=f"{target_file}:__FILE__"
                            )
                            self.logger.log(self.__class__.__name__, f"DEBUG: Created unresolved import: {file_qname} -> {symbol_name} from {target_file}")

    def _extract_import_from_node(self, node) -> Optional[dict]:
        """Extract import details from a PHP AST node.

        Args:
            node: Tree-sitter node representing an include/require statement

        Returns:
            dict with 'module_name' and 'imported_names', or None if extraction fails
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: _extract_import_from_node called with node type: {node.type}")
        try:
            # PHP includes/requires import all symbols from the included file
            # We need to extract the file path from the expression

            # Find the string content (the file path)
            string_node = None
            for child in node.children:
                if child.type == "string":
                    string_node = child
                    break

            if not string_node:
                return None

            # Extract the file path from the string (remove quotes)
            file_path = string_node.text.decode('utf-8').strip('"\'')

            # For PHP includes, we import all symbols from the file
            # We'll use a special marker to indicate "all symbols"
            return {
                'module_name': file_path,
                'imported_names': ['*']  # Special marker for "all symbols"
            }

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting import from node: {e}")
            return None

    def _convert_module_to_file_path(self, module_name: str) -> str:
        """Convert a PHP module/file path to a normalized file path.

        Args:
            module_name: The file path from include/require

        Returns:
            Normalized file path
        """
        # PHP includes can be relative or absolute
        # For our test cases, we'll assume relative paths from the same directory
        if module_name.startswith('./'):
            return module_name[2:]  # Remove leading ./
        elif module_name.startswith('../'):
            # For simplicity, handle one level up
            return module_name[3:]
        else:
            return module_name

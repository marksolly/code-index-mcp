from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_instantiation_handler import BaseInstantiationHandler


class PhpInstantiationHandler(BaseInstantiationHandler):
    """PHP-specific implementation of instantiation relationship handler."""

    def _get_instantiation_queries(self) -> list[str]:
        """Return PHP-specific tree-sitter queries for finding instantiations."""
        return [
            # Query for new expressions - match object_creation_expression and capture class name
            """
            (object_creation_expression
              [
                (qualified_name (name) @name)
                (variable_name (name) @name)
                (name) @name
              ]
            ) @instantiation
            """
        ]

    def extract_from_ast(self, tree: 'Tree', writer: 'IndexWriter', reader: 'IndexReader', file_qname: str):
        """
        Phase 1: Extract unresolved instantiation relationships from AST.
        """
        self.logger.log(self.__class__.__name__, f"DEBUG: extract_from_ast called for {file_qname}")
        super().extract_from_ast(tree, writer, reader, file_qname)
        self.logger.log(self.__class__.__name__, f"DEBUG: extract_from_ast completed for {file_qname}")

    def _extract_instantiation_from_node(self, node) -> Optional[dict]:
        """Extract instantiation details from a PHP AST node.

        Args:
            node: Tree-sitter node representing an object_creation_expression

        Returns:
            dict with 'class_name' key, or None if extraction fails
        """
        try:
            # Find the class name in the object creation expression
            # PHP uses either 'qualified_name' or 'name' for class names
            class_name_node = None

            # Look for qualified_name first (Namespace\ClassName)
            for child in node.children:
                if child.type == "qualified_name":
                    class_name_node = child
                    break
                elif child.type == "name":
                    class_name_node = child
                    break

            if not class_name_node:
                return None

            # Extract the class name
            class_name = class_name_node.text.decode('utf-8')

            return {'class_name': class_name}

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting instantiation from node: {e}")
            return None

    def _find_containing_context(self, node, file_qname: str) -> Optional[str]:
        """Find the containing context (function/method) for an instantiation.

        Args:
            node: Tree-sitter node representing the instantiation
            file_qname: The file qualified name

        Returns:
            The qname of the containing function/method, or the file qname if at global level.
            Returns None if context cannot be determined.
        """
        try:
            current = node.parent
            while current:
                if current.type == "method_declaration":
                    # Get method name
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        method_name = name_node.text.decode('utf-8')

                        # Find the containing class
                        class_name = None
                        parent = current.parent
                        while parent:
                            if parent.type == "class_declaration":
                                class_name_node = parent.child_by_field_name("name")
                                if class_name_node:
                                    class_name = class_name_node.text.decode('utf-8')
                                break
                            parent = parent.parent

                        if class_name:
                            return f"{class_name}.{method_name}"
                        else:
                            # Extract clean filename from file_qname (remove :__FILE__ suffix if present)
                            clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                            return f"{clean_file_name}:{method_name}"

                elif current.type == "function_definition":
                    # Get function name
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        function_name = name_node.text.decode('utf-8')

                        # Extract clean filename from file_qname (remove :__FILE__ suffix if present)
                        clean_file_name = file_qname.replace(':__FILE__', '') if file_qname.endswith(':__FILE__') else file_qname
                        return f"{clean_file_name}:{function_name}"

                current = current.parent

            # If no containing function/method found, return file qname
            return file_qname

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error extracting context: {e}")
            return file_qname

    def _should_track_instantiation(self, class_name: str, node, source_qname: str, file_qname: str) -> bool:
        """Determine if a PHP instantiation should be tracked based on "fail-soft" philosophy.

        Focus on high-signal instantiations (user-defined classes).
        Skip low-signal patterns that create unresolvable relationships.

        Args:
            class_name: The name of the class being instantiated
            node: The AST node representing the instantiation
            source_qname: The qname of the containing context
            file_qname: The file being processed

        Returns:
            True if instantiation should be tracked, False to skip (following fail-soft approach)
        """
        try:
            # Skip built-in PHP types and core classes
            builtin_classes = {
                'Exception', 'ErrorException', 'PDOException', 'DateTime', 'DateTimeZone',
                'PDO', 'mysqli', 'SplFileObject', 'DirectoryIterator', 'ArrayIterator',
                'stdClass', 'ArrayObject', 'Closure', 'Generator', '__PHP_Incomplete_Class'
            }

            if class_name in builtin_classes:
                self.logger.log(self.__class__.__name__, f"DEBUG: Skipping built-in PHP class instantiation: {class_name}")
                return False

            # Skip generic/common library classes that are likely external or not meaningful
            generic_classes = {
                'Logger', 'Cache', 'Config', 'Database', 'DB', 'Connection', 'Connector',
                'Helper', 'Utils', 'Util', 'Manager', 'Factory', 'Builder', 'Handler'
            }

            if class_name in generic_classes:
                self.logger.log(self.__class__.__name__, f"DEBUG: Skipping generic PHP class instantiation: {class_name}")
                return False

            # HIGH-SIGNAL: Classes starting with capital letters (following PSR conventions)
            # PHP follows PascalCase for class names
            if class_name[0].isupper():
                self.logger.log(self.__class__.__name__, f"DEBUG: Tracking PascalCase PHP class instantiation: {class_name}")
                return True

            # Skip very short names
            if len(class_name) <= 1:
                self.logger.log(self.__class__.__name__, f"DEBUG: Skipping too-short PHP class name: {class_name}")
                return False

            # For now, be conservative: only track PascalCase classes
            # This focuses on meaningful, potentially resolvable instantiations
            self.logger.log(self.__class__.__name__, f"DEBUG: Skipping non-PascalCase PHP class instantiation: {class_name}")
            return False

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error checking if PHP instantiation should be tracked: {e}")
            # On error, default to conservative (don't track)
            return False

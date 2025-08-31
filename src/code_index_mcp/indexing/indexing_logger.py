import inspect
import importlib
import os
from typing import Any, Dict, List

# src/code_index_mcp/utils/indexing_logger.py

class ComponentRegistry:
    """Automatically discovers and manages relationship type -> component mappings."""

    _component_map = None
    _reverse_map = None

    @classmethod
    def _build_component_maps(cls):
        """Build the component mapping tables through introspection."""
        if cls._component_map is not None:
            return

        cls._component_map = {}  # relationship_type -> [component_names]
        cls._reverse_map = {}    # component_name -> relationship_type

        # Base directory for relationship handlers
        handler_base = "src.code_index_mcp.indexing.relationship_handlers"

        # Scan language directories
        for language_dir in ["javascript", "python"]:
            try:
                # Get the directory path
                lang_dir_path = os.path.join(os.path.dirname(__file__), "relationship_handlers", language_dir)

                if os.path.exists(lang_dir_path):
                    # Find all Python files in the directory
                    for filename in os.listdir(lang_dir_path):
                        if filename.endswith('.py') and not filename.startswith('__'):
                            module_name = f"{handler_base}.{language_dir}.{filename[:-3]}"

                            try:
                                module = importlib.import_module(module_name)

                                # Find all classes in this module
                                for name, obj in inspect.getmembers(module):
                                    if inspect.isclass(obj):
                                        # Check if this class or any of its base classes has relationship_type
                                        rel_type = None
                                        component_name = obj.__name__

                                        # Check the class itself first
                                        if hasattr(obj, 'relationship_type'):
                                            rel_type = obj.relationship_type
                                        else:
                                            # Check base classes in MRO
                                            for base in inspect.getmro(obj):
                                                if (hasattr(base, 'relationship_type') and
                                                    base.relationship_type and
                                                    base.__name__ != 'BaseRelationshipHandler'):
                                                    rel_type = base.relationship_type
                                                    break

                                        if rel_type:
                                            # Add to relationship_type -> components mapping
                                            if rel_type not in cls._component_map:
                                                cls._component_map[rel_type] = []
                                            if component_name not in cls._component_map[rel_type]:
                                                cls._component_map[rel_type].append(component_name)

                                            # Add to reverse mapping
                                            cls._reverse_map[component_name] = rel_type

                                            # Also include base class if it exists and has relationship_type
                                            if hasattr(obj, '__bases__'):
                                                for base in obj.__bases__:
                                                    if ('Base' in base.__name__ and
                                                        'Handler' in base.__name__ and
                                                        hasattr(base, 'relationship_type') and
                                                        base.relationship_type):

                                                        base_rel_type = base.relationship_type
                                                        if base_rel_type not in cls._component_map:
                                                            cls._component_map[base_rel_type] = []
                                                        if base.__name__ not in cls._component_map[base_rel_type]:
                                                            cls._component_map[base_rel_type].append(base.__name__)

                                                        cls._reverse_map[base.__name__] = base_rel_type

                            except ImportError:
                                continue

            except Exception:
                continue

    @classmethod
    def get_components_for_relationship(cls, relationship_type: str) -> List[str]:
        """Get all component names that handle a specific relationship type."""
        cls._build_component_maps()
        return cls._component_map.get(relationship_type, [])

    @classmethod
    def get_relationship_for_component(cls, component_name: str) -> str:
        """Get the relationship type handled by a component."""
        cls._build_component_maps()
        return cls._reverse_map.get(component_name, "")

    @classmethod
    def get_all_relationship_types(cls) -> List[str]:
        """Get all known relationship types."""
        cls._build_component_maps()
        return list(cls._component_map.keys())


class IndexingLogger:
    def __init__(self, enabled=False, filters=None):
        """
        Initializes the logger.
        'filters' is a dict that controls output. For example:
        {
            'language': ['python'],
            'symbol_names': ['get_user', 'update_user'],  # Legacy
            'component_names': ['PythonImportHandler', 'BaseImportHandler']  # New
        }
        """
        self.enabled = enabled
        self.filters = filters or {}
        self.current_context = {}

        print(f"Logger initialized with filters: {self.filters}")

    def set_context(self, **context):
        """
        Called by the orchestrator to set the context for a file run.
        Must contain ['language'].
        """
        self.current_context = context

    def mustLog(self, component_name, message, **dump_vars):
        """Logs a message always, regardless of filters."""
        if not self.enabled:
            return

        full_context = {**dump_vars}

        formatted_message = self._format_message(component_name, message, full_context)
        print(formatted_message)


    def mustLogForLang(self, component_name, message, **dump_vars):
        """Logs a message if the language filter matches, regardless of other filters."""
        if not self.enabled:
            return
        
        full_context = {**dump_vars}

        # Check language filter
        if self.filters and self.current_context['language'] and 'language' in self.filters:
            if self.current_context['language'] in self.filters['language']:
                print(self._format_message(component_name, message, full_context))
            else:
                #print(F"Ignored, lang: {message}")
                return

    def log(self, component_name: str, message: str, **dump_vars: Dict[str, Any]):
        """Logs a message if it passes the filters."""
        if not self.enabled:
            return

        formatted_message = self._format_message(component_name, message, dump_vars)
        if self._should_log(component_name, formatted_message, self.current_context.get('language')):
            print(formatted_message)

    def _should_log(self, component_name: str, message: str, language: str = None):
        """
        The core filtering logic. A message is logged only if it matches ALL
        provided filters.
        """
        if not self.filters:
            return True  # No filters means log everything

        # Check language filter
        if language and 'language' in self.filters:
            if language not in self.filters['language']:
                return False

        # Check component name filter (fast exact match)
        if 'component_names' in self.filters:
            if component_name in self.filters['component_names']:
                return True
            else:
                return False

        # Check symbol name filter (slower string search)
        if 'symbol_names' in self.filters:
            for symbol in self.filters['symbol_names']:
                if symbol in message:
                    return True
            return False

        # If unsure, log it!
        return True

    def _format_message(self, component_name, message, dump_vars):
        """Creates a clean, structured log line."""
        dump_str = ", ".join(f"{k}='{v}'" for k, v in dump_vars.items())
        return f"{component_name}: {message} {dump_str}"

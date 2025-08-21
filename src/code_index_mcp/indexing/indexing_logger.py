from typing import Any, Dict

# src/code_index_mcp/utils/indexing_logger.py

class IndexingLogger:
    def __init__(self, enabled=False, filters=None):
        """
        Initializes the logger.
        'filters' is a dict that controls output. For example:
        {
            'language': ['python'],
            'symbol_names': ['get_user', 'update_user']
        }
        """
        self.enabled = enabled
        self.filters = filters or {}
        self.current_context = {}

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

        full_context = {**self.current_context, **dump_vars}

        formatted_message = self._format_message(component_name, message, full_context)
        print(formatted_message)

    def log(self, component_name: str, message: str, **dump_vars: Dict[str, Any]):
        """Logs a message if it passes the filters."""
        if not self.enabled:
            return

        formatted_message = self._format_message(component_name, message, dump_vars)
        if self._should_log(formatted_message, self.current_context['language']):
            print(formatted_message)

    def _should_log(self, message, language):
        """
        The core filtering logic. A message is logged only if it matches ALL
        provided filters.
        """
        #return True
        if not self.filters:
            return True  # No filters means log everything

        # Check language filter
        if language and 'language' in self.filters:
            if language not in self.filters['language']:
                #print(F"Ignored, lang: {message}")
                return False

        # Check symbol name filter
        if 'symbol_names' in self.filters:
            for symbol in self.filters['symbol_names']:
                if(symbol in message):
                    return True
            #print(F"Ignored, no symbol: {message}")
            return False

        # If unsure, log it!        
        return True

    def _format_message(self, component_name, message, dump_vars):
        """Creates a clean, structured log line."""
        dump_str = ", ".join(f"{k}='{v}'" for k, v in dump_vars.items())
        return f"{component_name}: {message} {dump_str}"

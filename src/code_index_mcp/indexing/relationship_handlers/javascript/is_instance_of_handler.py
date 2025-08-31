from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_is_instance_of_handler import BaseIsInstanceOfHandler


class JavascriptIsInstanceOfHandler(BaseIsInstanceOfHandler):
    """JavaScript-specific implementation of is_instance_of relationship handler."""

    def _infer_variable_qname(self, source_qname: str, target_qname: str) -> Optional[str]:
        """Infer the variable qname from the instantiation context.

        Args:
            source_qname: The qname of the method/function where instantiation occurred
            target_qname: The qname of the class being instantiated

        Returns:
            The inferred variable qname, or None if cannot be inferred
        """
        try:
            # Parse the source_qname to understand the context
            parts = source_qname.split(':')
            if len(parts) < 2:
                self.logger.log(self.__class__.__name__, f"DEBUG: Invalid source_qname format: {source_qname}")
                return None

            file_path = parts[0]
            context = ':'.join(parts[1:])

            # Extract class name from target_qname for inference
            target_class_name = target_qname.split(':')[-1] if ':' in target_qname else target_qname

            # Infer variable name based on context
            if 'constructor' in context.lower():
                # In constructor: likely this.property_name
                # Use the class name but make it lowercase for property naming
                var_name = f"this.{target_class_name.lower()}"
                return f"{file_path}:{var_name}"
            elif context and context != 'program':
                # In a method or function: likely a local variable
                # Use the class name but make it lowercase for variable naming
                var_name = target_class_name.lower()
                # For method context, create a simple variable name without nested context
                return f"{file_path}:{var_name}"
            else:
                # At module level: module-level variable
                var_name = target_class_name.lower()
                return f"{file_path}:{var_name}"

        except Exception as e:
            self.logger.log(self.__class__.__name__, f"DEBUG: Error inferring variable qname: {e}")
            return None

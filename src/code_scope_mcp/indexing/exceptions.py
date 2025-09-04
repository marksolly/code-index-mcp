"""
Custom exceptions for the indexing module.
"""

class StrictModeViolationException(Exception):
    """
    Exception raised when strict resolution mode is enabled and unresolved relationships are found.

    This exception contains detailed information about the unresolved relationships
    to help with debugging and provide targeted information about what needs to be fixed.
    """

    def __init__(self, message: str, unresolved_relationships: list = None, handler_name: str = None):
        """
        Initialize the exception.

        Args:
            message: Human-readable error message
            unresolved_relationships: List of unresolved relationship details
            handler_name: Name of the handler that left unresolved relationships (if applicable)
        """
        super().__init__(message)
        self.unresolved_relationships = unresolved_relationships or []
        self.handler_name = handler_name
        self.message = message

    def __str__(self):
        """Return the string representation of the exception."""
        parts = [f"STRICT MODE VIOLATION: {self.message}"]

        if self.handler_name:
            parts.append(f"Handler: {self.handler_name}")

        if self.unresolved_relationships:
            parts.append(f"Unresolved relationships: {len(self.unresolved_relationships)}")
            for rel in self.unresolved_relationships[:5]:  # Show first 5 for brevity
                parts.append(f"  - {rel}")
            if len(self.unresolved_relationships) > 5:
                parts.append(f"  ... and {len(self.unresolved_relationships) - 5} more")

        return "\n".join(parts)

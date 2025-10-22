"""
Custom exceptions for the indexing module.
"""

class DuplicateRelationshipException(Exception):
    """
    Exception raised when attempting to insert a duplicate relationship.
    Contains details about both the attempted and existing relationships.
    """

    def __init__(self, source_id: int, target_id: int, type_id: int, existing_rel_details: tuple = None):
        self.source_id = source_id
        self.target_id = target_id
        self.type_id = type_id
        self.existing_rel_details = existing_rel_details  # (rel_type, source_qname, target_qname) if found

        message = f"Duplicate relationship detected: source_id={source_id}, target_id={target_id}, type_id={type_id}"
        if existing_rel_details:
            existing_rel_type, existing_source_qname, existing_target_qname = existing_rel_details
            message += f". Existing relationship: {existing_source_qname} --({existing_rel_type})--> {existing_target_qname}"

        super().__init__(message)


class DuplicateSymbolException(Exception):
    """
    Exception raised when attempting to insert a duplicate symbol.
    Contains details about the symbol that caused the constraint violation.
    """

    def __init__(self, file_id: int, qname: str, attempted_symbol: dict, file_path: str = None):
        self.file_id = file_id
        self.qname = qname
        self.attempted_symbol = attempted_symbol  # {'name': str, 'symbol_type': str, 'line_number': int}
        self.file_path = file_path

        message = f"Duplicate symbol detected: qname='{qname}' in file '{file_path or file_id}'"
        if attempted_symbol:
            message += f". Attempted: {attempted_symbol['name']} ({attempted_symbol['symbol_type']}) on line {attempted_symbol['line_number']}"

        super().__init__(message)


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

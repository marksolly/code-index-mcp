from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Tree

from ..common.base_inherits_handler import BaseInheritsHandler


class PhpInheritsHandler(BaseInheritsHandler):
    """PHP-specific implementation of inheritance relationship handler."""

    def _get_inheritance_symbol_types(self) -> list[str]:
        """Return the symbol types that represent inheritable constructs in PHP.

        In PHP, classes can be inherited from.
        """
        return ['class']

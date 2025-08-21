from .generic_name_based_resolver import GenericNameBasedResolverAnalyzer


class GenericInheritsAnalyzer(GenericNameBasedResolverAnalyzer):
    """
    A generic analyzer for 'inherits' relationships.

    This analyzer identifies relationships where a class inherits from another
    class. It inherits the name-based resolution logic from
    `GenericNameBasedResolverAnalyzer`.
    """

    relationship_type = "inherits"

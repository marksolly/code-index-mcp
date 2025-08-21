from .generic_name_based_resolver import GenericNameBasedResolverAnalyzer


class GenericIsInstanceOfAnalyzer(GenericNameBasedResolverAnalyzer):
    """
    A generic analyzer for 'is_instance_of' relationships.

    This analyzer identifies relationships where a variable is an instance of a
    class. It inherits the name-based resolution logic from
    `GenericNameBasedResolverAnalyzer`.
    """

    relationship_type = "is_instance_of"

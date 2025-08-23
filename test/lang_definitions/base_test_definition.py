import os
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from collections import defaultdict, deque

class BaseTestDefinition(ABC):
    """
    Abstract base class for language-specific test definitions.
    """

    @property
    @abstractmethod
    def language_name(self) -> str:
        """The name of the programming language."""
        pass

    @property
    def supported_relationships(self) -> List[str]:
        """
        A list of relationship types supported by the language.
        By default, this is automatically generated from relationship_dependencies.
        Override this property if you need to support relationships that don't have dependencies defined.
        """
        # Automatically generate from relationship_dependencies
        dependencies = self.relationship_dependencies
        if dependencies:
            return list(dependencies.keys())
        return []

    @property
    def relationship_dependencies(self) -> Dict[str, List[str]]:
        """
        Defines prerequisite relationships for each relationship type.
        Keys are relationship types, values are lists of relationship types
        that must be resolved before this one can be tested.

        Example:
        {
            'calls_class_method': ['imports', 'declares_class', 'declares_class_method'],
            'inherits': ['declares_class'],
        }
        """
        return {}

    @abstractmethod
    def get_sample_files(self) -> List[str]:
        """Returns a list of paths to the sample code files for the language."""
        pass

    def get_files_to_index(self) -> List[tuple[str, str, str]]:
        """
        Reads sample files and returns them in the format expected by the orchestrator.
        """
        files = []
        for file_path in self.get_sample_files():
            with open(file_path, 'r') as f:
                files.append((os.path.abspath(file_path), self.language_name, f.read()))
        return files

    def get_expected_relationships(self) -> List[Dict[str, Any]]:
        """
        Returns a list of dictionaries, each representing an expected relationship.
        Relationships are automatically sorted by dependency order to ensure tests
        run in the correct logical sequence.

        Each dictionary should have the following keys, in this order:
        - 'source': The name of the source symbol.
        - 'source_qname': The qualified name of the source symbol.
        - 'type': The type of the relationship.
        - 'target': The name of the target symbol.
        - 'target_qname': The qualified name of the target symbol.
        - 'count': The expected number of times this relationship should appear.

        """
        relationships = self._define_expected_relationships()

        # Validate and enrich relationships
        for rel in relationships:
            self._validate_qname(rel.get('source_qname'), f"source_qname in {self.language_name} test definition")
            self._validate_qname(rel.get('target_qname'), f"target_qname in {self.language_name} test definition")
            required_fields = ['type', 'source_qname', 'target_qname', 'count']
            for field in required_fields:
                if field not in rel or rel[field] is None:
                    raise ValueError(f"Missing or None required field '{field}' in relationship: {rel}")
            # Auto-generate 'source' and 'target' from qnames
            rel['source'] = self._extract_name_from_qname(rel['source_qname'])
            rel['target'] = self._extract_name_from_qname(rel['target_qname'])

        # Sort relationships by dependency order
        return self._sort_relationships_by_dependencies(relationships)

    @abstractmethod
    def _define_expected_relationships(self) -> List[Dict[str, Any]]:
        """
        Internal method to be implemented by subclasses to return the raw list of expected relationships.
        """
        pass

    QNAME_VALIDATION_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\/]+(:|\.|:__FILE__)[a-zA-Z0-9_\-]*$")

    def _validate_qname(self, qname: str, context: str):
        if qname is None:
            return # Qname is optional in some cases

        # Allow file qnames, which don't have a separator but must contain a dot (for file extension)
        if ":" not in qname and "." not in qname:
            print(f"Invalid qname format in {context}: '{qname}' - symbol qnames must have a separator (: or .)")
            raise ValueError(f"Invalid qname format in {context}: '{qname}' - symbol qnames must have a separator (: or .)")

        # For qnames without separator, ensure they are valid file names (contain extension)
        if ":" not in qname and "." not in qname:
            if "." not in qname:
                print(f"Invalid file qname format in {context}: '{qname}' - file qnames must contain a dot for extension")
                raise ValueError(f"Invalid file qname format in {context}: '{qname}' - file qnames must contain a dot for extension")
            return

        if not self.QNAME_VALIDATION_REGEX.match(qname):
            print(f"Invalid qname format in {context}: '{qname}'")
            raise ValueError(f"Invalid qname format in {context}: '{qname}'")

    def _extract_name_from_qname(self, qname: str) -> str:
        """
        Extracts the symbol name from a qualified name.
        For qnames with separators (: or .), returns the part after the last separator.
        For file qnames ending with :__FILE__, returns the filename without the suffix.
        For qnames without separators (file names), returns the whole qname.
        """
        if qname.endswith(':__FILE__'):
            return qname[:-9]  # Remove ':__FILE__' suffix (including the colon)
        elif ":" in qname:
            return qname.split(":")[-1]
        elif "." in qname:
            return qname.split(".")[-1]
        else:
            return qname

    def _sort_relationships_by_dependencies(self, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sorts relationships by dependency order using topological sorting.
        Builds a dependency graph from relationship_dependencies and performs
        topological sort to ensure proper execution order.

        Args:
            relationships: List of relationship dictionaries

        Returns:
            Sorted list of relationships in dependency order
        """
        if not relationships:
            return []

        # Get dependency mapping
        deps = self.relationship_dependencies

        # Collect all unique relationship types present in the data
        all_types = set()
        relationships_by_type = defaultdict(list)

        for rel in relationships:
            rel_type = rel['type']
            all_types.add(rel_type)
            relationships_by_type[rel_type].append(rel)

        # Separate calls relationships to ensure they run last
        calls_types = {t for t in all_types if 'calls' in t.lower()}
        non_calls_types = all_types - calls_types

        # Build dependency graph for non-calls types
        graph = defaultdict(list)  # type -> list of types that depend on it
        in_degree = defaultdict(int)  # type -> number of dependencies

        # Initialize in_degree for all non-calls types
        for rel_type in non_calls_types:
            in_degree[rel_type] = 0

        # Build the graph and calculate in_degrees
        for rel_type in non_calls_types:
            if rel_type in deps:
                for dep in deps[rel_type]:
                    # Only consider dependencies that exist in our dataset
                    if dep in non_calls_types:
                        graph[dep].append(rel_type)
                        in_degree[rel_type] += 1

        # Perform topological sort using Kahn's algorithm
        # Use a stable sort to ensure deterministic ordering when multiple types have same in-degree
        queue = deque(sorted([t for t in non_calls_types if in_degree[t] == 0], key=lambda x: x))
        sorted_types = []

        while queue:
            current = queue.popleft()
            sorted_types.append(current)

            for dependent in graph[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    # Insert in sorted order to maintain deterministic behavior
                    # Find the correct position to insert the dependent
                    insert_pos = 0
                    for i, item in enumerate(queue):
                        if dependent < item:
                            insert_pos = i
                            break
                        insert_pos = i + 1
                    queue.insert(insert_pos, dependent)

        # Add any remaining types that might have circular dependencies
        remaining_types = non_calls_types - set(sorted_types)
        sorted_types.extend(sorted(remaining_types, key=lambda x: x))

        # Add calls types at the end
        sorted_types.extend(sorted(calls_types, key=lambda x: x))

        # Reconstruct relationships in dependency order
        sorted_relationships = []
        for rel_type in sorted_types:
            # Sort relationships within the same type by a stable key for deterministic ordering
            type_relationships = relationships_by_type[rel_type]
            type_relationships.sort(key=lambda r: (r['source_qname'], r['target_qname']))
            sorted_relationships.extend(type_relationships)

        # Add execution order index to ensure unittest runs tests in correct order
        for i, rel in enumerate(sorted_relationships):
            rel['_execution_order'] = i

        return sorted_relationships

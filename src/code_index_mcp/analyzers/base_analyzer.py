"""Base analyzer interface for language-specific code analysis."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import os
import re
from .analysis_result import AnalysisResult


class BaseAnalyzer(ABC):
    """Abstract base class for language-specific code analyzers."""

    @abstractmethod
    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze the content of a file and return structured information.

        Args:
            file_path: The relative path of the file

        Returns:
            A dictionary containing structured analysis information
        """
        pass

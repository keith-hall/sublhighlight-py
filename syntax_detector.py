"""
Syntax detection service for automatic syntax identification.
"""

import os
import regex as re
from typing import Optional, Dict, Any, TextIO

from sublsyntax import (
    loadsyntaxesmp,
    all_syntaxes_paths,
    loadsyntax_until,
)


class SyntaxDetector:
    """Handles automatic syntax detection from file extensions and content."""
    
    def __init__(self):
        self._syntaxes_cache: Optional[Dict[str, Any]] = None
    
    def detect_syntax(self, input_file: Optional[str], input_stream: TextIO) -> tuple[Optional[str], Optional[str]]:
        """
        Detect syntax from file extension or first line content.
        
        Args:
            input_file: Path to input file (if any)
            input_stream: Input stream to read from
            
        Returns:
            Tuple of (detected_syntax, first_line_read)
        """
        # Try file extension first
        if input_file:
            syntax = self._detect_from_extension(input_file)
            if syntax:
                return syntax, None
        
        # Try first line match
        return self._detect_from_first_line(input_stream)
    
    def _detect_from_extension(self, file_path: str) -> Optional[str]:
        """Detect syntax from file extension."""
        file_ext = os.path.splitext(file_path)[1].lstrip(".")
        
        syntaxes = self._get_syntaxes()
        for syntax_name, syntax in syntaxes.items():
            if syntax:
                file_extensions = syntax.get("file_extensions", [])
                if file_ext in file_extensions:
                    return syntax_name
        
        return None
    
    def _detect_from_first_line(self, input_stream: TextIO) -> tuple[Optional[str], Optional[str]]:
        """Detect syntax from first line pattern matching.
        
        Returns:
            Tuple of (detected_syntax, first_line_read)
        """
        syntaxes = self._get_syntaxes()
        
        for line in input_stream:
            for syntax_name, syntax in syntaxes.items():
                if syntax:
                    first_line_match = syntax.get("first_line_match", None)
                    if first_line_match:
                        if re.match(first_line_match, line):
                            return syntax_name, line
            return None, line  # Return the line even if no syntax matched
        
        return None, None
    
    def _get_syntaxes(self) -> Dict[str, Any]:
        """Get syntaxes with caching for performance."""
        if self._syntaxes_cache is None:
            fastloadpatts = (
                re.compile("^file_extensions:"),
                re.compile("^first_line_match")
            )
            self._syntaxes_cache = loadsyntaxesmp(
                all_syntaxes_paths,
                lambda path: loadsyntax_until(path, fastloadpatts, cache=False)
            )
        
        return self._syntaxes_cache
    
    def cleanup(self):
        """Clean up cached data."""
        self._syntaxes_cache = None
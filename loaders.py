"""
Loaders for syntax definitions and color schemes.
"""

import os
from typing import Dict, Any

from sublsyntax import (
    loadsyntax,
    parsesyntax,
    syntax_dir_path,
    file_ext as sublsynt_ext,
)
from sublcolorscheme import (
    loadcolorscheme,
    parsecolorscheme,
    color_scheme_dir_path,
    file_ext as sublcolscheme_ext,
)


class SyntaxLoader:
    """Handles loading and caching of syntax definitions."""
    
    def __init__(self):
        self._syntax_cache: Dict[str, Any] = {}
        self._syntaxes_by_scope: Dict[str, Any] = {}
    
    def load_syntax(self, syntax_name: str) -> Dict[str, Any]:
        """
        Load and parse a syntax definition by name.
        
        Args:
            syntax_name: Name of the syntax to load
            
        Returns:
            Parsed syntax definition
        """
        if syntax_name in self._syntax_cache:
            return self._syntax_cache[syntax_name]
        
        syntax_path = os.path.abspath(
            os.path.join(
                syntax_dir_path,
                f"{syntax_name}.{sublsynt_ext}"
            )
        )
        
        syntax = parsesyntax(
            loadsyntax(syntax_path),
            postlazyloadsyntax=self._cache_scope_mapping
        )
        
        self._syntax_cache[syntax_name] = syntax
        return syntax
    
    def load_syntax_by_path(self, path: str) -> Dict[str, Any]:
        """
        Load and parse a syntax definition by file path.
        
        Args:
            path: Path to syntax file
            
        Returns:
            Parsed syntax definition
        """
        if path in self._syntax_cache:
            return self._syntax_cache[path]
        
        syntax = parsesyntax(
            loadsyntax(path),
            postlazyloadsyntax=self._cache_scope_mapping
        )
        
        self._syntax_cache[path] = syntax
        return syntax
    
    def load_syntax_by_scope(self, syntax_scope: str) -> Dict[str, Any]:
        """
        Load syntax by scope identifier.
        
        Args:
            syntax_scope: Scope identifier for the syntax
            
        Returns:
            Parsed syntax definition or None if not found
        """
        if syntax_scope in self._syntaxes_by_scope:
            return self._syntaxes_by_scope[syntax_scope]
        
        # Import here to avoid circular imports
        import regex as re
        from sublsyntax import all_syntaxes_paths
        
        scope_regex = re.compile(fr"^scope:[ ]*{syntax_scope}", re.IGNORECASE)
        for path in all_syntaxes_paths:
            try:
                with open(path, "r", encoding="latin1") as f:
                    for line in f:
                        if scope_regex.match(line):
                            return self.load_syntax_by_path(path)
            except (OSError, IOError):
                continue
        
        return None
    
    def _cache_scope_mapping(self, syntax: Dict[str, Any]) -> None:
        """Cache syntax by its scope for quick lookups."""
        if "scope" in syntax:
            self._syntaxes_by_scope[syntax["scope"]] = syntax


class ColorSchemeLoader:
    """Handles loading and caching of color schemes."""
    
    def __init__(self):
        self._scheme_cache: Dict[str, Any] = {}
    
    def load_color_scheme(self, scheme_name: str) -> Dict[str, Any]:
        """
        Load and parse a color scheme by name.
        
        Args:
            scheme_name: Name of the color scheme to load
            
        Returns:
            Parsed color scheme
        """
        if scheme_name in self._scheme_cache:
            return self._scheme_cache[scheme_name]
        
        scheme_path = os.path.abspath(
            os.path.join(
                color_scheme_dir_path,
                f"{scheme_name}.{sublcolscheme_ext}"
            )
        )
        
        scheme = parsecolorscheme(
            loadcolorscheme(scheme_path)
        )
        
        self._scheme_cache[scheme_name] = scheme
        return scheme
"""
Output writer for formatted syntax highlighting.
"""

from typing import Dict, Any, List, Tuple, TextIO
from math import floor, ceil

from scsast import scorexp
from sublcolorsys import (
    rgba_to_ansi256,
    hlsa_to_rgba,
    rgba_to_hlsa,
    hlsa_lerp,
    term_color,
)
from config import DebugConfig


class OutputWriter:
    """Handles formatted output with color and styling."""
    
    def __init__(self, color_scheme: Dict[str, Any], output: TextIO, debug_config: DebugConfig):
        self.color_scheme = color_scheme
        self.output = output
        self.debug_config = debug_config
        self._token_color_cache: Dict[int, Tuple[int, int]] = {}
    
    def get_token_color(self, token: str, scopestack: List[List[str]]) -> Tuple[int, int]:
        """
        Get color for a token based on current scope stack.
        
        Args:
            token: Token text (can be None)
            scopestack: Current scope stack
            
        Returns:
            Tuple of (foreground_color, background_color)
        """
        cache_key = hash((*(y for x in scopestack for y in x), token))
        if cache_key in self._token_color_cache:
            cached_result = self._token_color_cache[cache_key]
            self.debug_config.debug(f"token_color: token: {repr(token)} cached: {cached_result}")
            return cached_result
        
        globals_config = self.color_scheme["globals"]
        rules = self.color_scheme["rules"]
        best_rule = None
        best_score = 0
        lenss = len(scopestack)
        
        self.debug_config.debug(f"token_color: token: {repr(token)} ss: {scopestack}")
        
        for rule in rules:
            xp = rule["scope"]
            score = scorexp(xp, scopestack, lenss)
            if score > 0 and (best_rule is None or score > best_score):
                best_rule = rule
                best_score = score
        
        if best_rule is not None:
            foreground = best_rule.get("foreground", globals_config["foreground"])
            self.debug_config.debug(f"token_color: token: {repr(token)} best rule: {best_rule} has gradient: {'yes' if isinstance(foreground, list) else 'no'}")
            
            if isinstance(foreground, list):
                foreground = self._calculate_gradient_color(foreground, token)
                self.debug_config.debug(f"token_color: token: {repr(token)} gradient color: {foreground}")
            
            entry = (
                rgba_to_ansi256(*foreground),
                rgba_to_ansi256(*best_rule.get("background", globals_config["background"]))
            )
        else:
            self.debug_config.debug(f"no matching rule for token: {repr(token)}")
            entry = (
                rgba_to_ansi256(*globals_config["foreground"]),
                rgba_to_ansi256(*globals_config["background"])
            )
        
        self._token_color_cache[cache_key] = entry
        return entry
    
    def _calculate_gradient_color(self, foreground_list: List, token: str) -> List[float]:
        """Calculate color from gradient based on token hash."""
        color_t = hash(token) % 255 / 255 if token else 0.0
        samp_t = color_t * len(foreground_list) - color_t
        
        start_color = rgba_to_hlsa(*foreground_list[int(floor(samp_t))])
        end_color = rgba_to_hlsa(*foreground_list[int(ceil(samp_t))])
        
        return hlsa_to_rgba(*hlsa_lerp(start_color, end_color, color_t))
    
    def set_color(self, foreground: int, background: int) -> None:
        """Set output color."""
        self.output.write(term_color(foreground, background))
    
    def write_token(self, token: str, scopestack: List[List[str]]) -> None:
        """
        Write a token with appropriate coloring.
        
        Args:
            token: Token text to write
            scopestack: Current scope stack for color calculation
        """
        token_color = self.get_token_color(token, scopestack)
        self.debug_config.debug(f"write_token: {repr(token)} color: {token_color}")
        self.set_color(*token_color)
        self.output.write(token)
    
    def write_raw(self, text: str) -> None:
        """Write raw text without color processing."""
        self.output.write(text)
    
    def flush(self) -> None:
        """Flush output buffer."""
        self.output.flush()
    
    def getvalue(self) -> str:
        """Get output value (for StringIO outputs)."""
        if hasattr(self.output, 'getvalue'):
            return self.output.getvalue()
        return ""
    
    def close(self) -> None:
        """Close output stream."""
        if hasattr(self.output, 'close'):
            self.output.close()
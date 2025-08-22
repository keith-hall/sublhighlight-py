"""
Pattern compilation for syntax highlighting.
"""

import regex as re
import onigurumacffi as oniguruma
from typing import Dict, Any

from managers import RuntimeContext


class PatternCompiler:
    """Handles compilation of regex patterns with variable substitution."""
    
    def __init__(self):
        self._re_varsub = re.compile(r"{{([A-Za-z0-9_]+)}}")
    
    def compile_pattern(self, pattern: str, rtctx: RuntimeContext):
        """
        Compile a pattern with variable substitution.
        
        Args:
            pattern: Pattern string possibly containing variables
            rtctx: Runtime context for variable lookup
            
        Returns:
            Compiled oniguruma pattern
        """
        original_pattern = pattern
        
        # Substitute variables
        while True:
            varnames = self._re_varsub.findall(pattern)
            if not varnames:
                break
            
            for varname in varnames:
                var_value = rtctx.syntax["variables"].get(varname, None)
                if var_value:
                    pattern = pattern.replace(f"{{{{{varname}}}}}", var_value, 1)
                else:
                    raise KeyError(f"variable: {varname} not found")
        
        try:
            compiled_pattern = oniguruma.compile(pattern)
            # Store original pattern for debugging
            compiled_pattern.pattern = original_pattern
            return compiled_pattern
        except Exception:
            print(f"errors compiling pattern: {original_pattern} => {pattern}")
            raise
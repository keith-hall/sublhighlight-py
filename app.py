"""
Main application class for syntax highlighter.
"""

import json
import sys
from io import StringIO
from typing import Optional

from config import AppConfig
from syntax_detector import SyntaxDetector
from loaders import SyntaxLoader, ColorSchemeLoader
from highlighter import ModernSyntaxHighlighter
from sublsyntax import all_syntaxes_names
from sublcolorscheme import all_color_schemes_names


class SyntaxHighlighterApp:
    """Main application class for the syntax highlighter."""
    
    def __init__(self):
        self.config: Optional[AppConfig] = None
        self.syntax_detector = SyntaxDetector()
        self.syntax_loader = SyntaxLoader()
        self.color_scheme_loader = ColorSchemeLoader()
    
    def run(self, args=None) -> None:
        """
        Run the syntax highlighter application.
        
        Args:
            args: Command line arguments (None for sys.argv)
        """
        try:
            self.config = AppConfig.from_args(args)
            
            # Handle listing options
            if self.config.list_syntaxes:
                self._list_syntaxes()
            
            if self.config.list_color_schemes:
                self._list_color_schemes()
            
            if self.config.should_exit_early():
                return
            
            # Detect syntax if not specified
            first_stdin_line = self._detect_syntax_if_needed()
            
            # Load syntax and color scheme
            syntax = self.syntax_loader.load_syntax(self.config.syntax or "Default")
            color_scheme = self.color_scheme_loader.load_color_scheme(self.config.color_scheme)
            
            # Set up output
            output = sys.stdout if not self.config.debug else StringIO()
            
            # Create and run highlighter
            highlighter = ModernSyntaxHighlighter(
                syntax=syntax,
                color_scheme=color_scheme,
                output=output,
                debug_config=self.config.debug_config,
                show_scopes=self.config.show_scopes,
                syntax_loader=self.syntax_loader
            )
            
            highlighter.begin()
            
            # Process first line if we read it for detection
            if first_stdin_line:
                highlighter.process(first_stdin_line)
                output.flush()
            
            # Process remaining lines
            for line in self.config.input_stream:
                highlighter.process(line)
                output.flush()
            
            highlighter.end()
            
            # Output debug information if needed
            if self.config.debug:
                print(output.getvalue())
                output.close()
                
        finally:
            self._cleanup()
    
    def _detect_syntax_if_needed(self) -> Optional[str]:
        """Detect syntax automatically if not specified."""
        first_line = None
        
        if self.config.syntax is None:
            detected_syntax, first_line = self.syntax_detector.detect_syntax(
                self.config.input_file,
                self.config.input_stream
            )
            
            if detected_syntax:
                self.config.syntax = detected_syntax
        
        return first_line
    
    def _list_syntaxes(self) -> None:
        """List available syntaxes."""
        print(json.dumps({"syntaxes": all_syntaxes_names}, indent=2))
    
    def _list_color_schemes(self) -> None:
        """List available color schemes.""" 
        print(json.dumps({"color-schemes": all_color_schemes_names}, indent=2))
    
    def _cleanup(self) -> None:
        """Clean up resources."""
        if self.config and self.config.input_stream != sys.stdin:
            self.config.input_stream.close()
        
        self.syntax_detector.cleanup()
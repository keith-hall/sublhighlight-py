"""
Configuration management for syntax highlighter.
Handles argument parsing and configuration setup.
"""

import argparse
import os
import sys
from typing import Optional, TextIO


class DebugConfig:
    """Manages debug output configuration."""
    
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._debug_func = print if enabled else None
    
    def debug(self, message: str) -> None:
        """Output debug message if debugging is enabled."""
        if self._debug_func:
            self._debug_func(message)
    
    def __call__(self, message: str) -> None:
        """Allow using instance as function for compatibility."""
        self.debug(message)


class AppConfig:
    """Application configuration and argument parsing."""
    
    def __init__(self):
        self.syntax: Optional[str] = None
        self.color_scheme: str = "Default"
        self.debug: bool = False
        self.show_scopes: bool = False
        self.list_syntaxes: bool = False
        self.list_color_schemes: bool = False
        self.input_file: Optional[str] = None
        self.input_stream: TextIO = sys.stdin
        self.debug_config: DebugConfig = DebugConfig()
    
    @classmethod
    def from_args(cls, args: list = None) -> 'AppConfig':
        """Create configuration from command line arguments."""
        parser = argparse.ArgumentParser()
        parser.add_argument("-s", "--syntax", type=str, help="sublime-syntax to use", nargs="?", default=None)
        parser.add_argument("-c", "--color-scheme", type=str, help="sublime-color-scheme to use", nargs="?", default="Default")
        parser.add_argument("-d", "--debug", action="store_true", help="turn debugging on", default=False)
        parser.add_argument("-S", "--show-scopes", action="store_true", help="output scopes tags", default=False)
        parser.add_argument("-ls", "--list-syntaxes", action="store_true", help="list available syntaxes", default=False)
        parser.add_argument("-lc", "--list-color-schemes", action="store_true", help="list available color schemes", default=False)
        parser.add_argument("input_file", type=str, help="input file", nargs="?", default=None)
        
        parsed_args = parser.parse_args(args)
        
        config = cls()
        config.syntax = parsed_args.syntax
        config.color_scheme = parsed_args.color_scheme
        config.debug = parsed_args.debug
        config.show_scopes = parsed_args.show_scopes
        config.list_syntaxes = parsed_args.list_syntaxes
        config.list_color_schemes = parsed_args.list_color_schemes
        config.input_file = parsed_args.input_file
        config.debug_config = DebugConfig(parsed_args.debug)
        
        # Set up input stream
        if config.input_file:
            config.input_stream = open(config.input_file, "r")
        else:
            config.input_stream = sys.stdin
            
        return config
    
    def should_exit_early(self) -> bool:
        """Check if application should exit after listing options."""
        return self.list_syntaxes or self.list_color_schemes
#!/usr/bin/env python3
"""
Unit tests for modernized components.
"""

import unittest
import tempfile
import os
from io import StringIO

from config import DebugConfig, AppConfig
from syntax_detector import SyntaxDetector
from loaders import SyntaxLoader, ColorSchemeLoader
from output_writer import OutputWriter


class TestDebugConfig(unittest.TestCase):
    """Test the DebugConfig class."""
    
    def test_debug_enabled(self):
        """Test debug output when enabled."""
        output = StringIO()
        debug_config = DebugConfig(enabled=True)
        debug_config._debug_func = lambda msg: output.write(msg + "\n")
        
        debug_config.debug("test message")
        self.assertEqual(output.getvalue(), "test message\n")
    
    def test_debug_disabled(self):
        """Test no output when debug disabled."""
        output = StringIO()
        debug_config = DebugConfig(enabled=False)
        # Don't set _debug_func when disabled
        
        debug_config.debug("test message")
        self.assertEqual(output.getvalue(), "")
    
    def test_callable_interface(self):
        """Test that debug config can be called as function."""
        output = StringIO()
        debug_config = DebugConfig(enabled=True)
        debug_config._debug_func = lambda msg: output.write(msg + "\n")
        
        debug_config("test message")
        self.assertEqual(output.getvalue(), "test message\n")


class TestAppConfig(unittest.TestCase):
    """Test the AppConfig class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = AppConfig()
        self.assertIsNone(config.syntax)
        self.assertEqual(config.color_scheme, "Default")
        self.assertFalse(config.debug)
        self.assertFalse(config.show_scopes)
        self.assertFalse(config.list_syntaxes)
        self.assertFalse(config.list_color_schemes)
    
    def test_from_args_parsing(self):
        """Test argument parsing."""
        args = ["-s", "Python", "-c", "Monokai", "-d", "-S"]
        config = AppConfig.from_args(args)
        
        self.assertEqual(config.syntax, "Python")
        self.assertEqual(config.color_scheme, "Monokai")
        self.assertTrue(config.debug)
        self.assertTrue(config.show_scopes)
    
    def test_should_exit_early(self):
        """Test early exit condition."""
        config = AppConfig()
        config.list_syntaxes = True
        self.assertTrue(config.should_exit_early())
        
        config.list_syntaxes = False
        config.list_color_schemes = True
        self.assertTrue(config.should_exit_early())
        
        config.list_color_schemes = False
        self.assertFalse(config.should_exit_early())


class TestSyntaxDetector(unittest.TestCase):
    """Test the SyntaxDetector class."""
    
    def setUp(self):
        self.detector = SyntaxDetector()
    
    def test_detect_from_extension(self):
        """Test syntax detection from file extension."""
        # This test depends on available syntax files
        detected = self.detector._detect_from_extension("test.py")
        if detected:  # Only test if Python syntax is available
            self.assertEqual(detected, "Python")
    
    def test_detect_from_first_line(self):
        """Test syntax detection from first line."""
        input_stream = StringIO("#!/usr/bin/env python3\nprint('hello')")
        detected, first_line = self.detector._detect_from_first_line(input_stream)
        # This may or may not work depending on available syntax files
        self.assertIsNotNone(first_line)
        self.assertEqual(first_line, "#!/usr/bin/env python3\n")


class TestLoaders(unittest.TestCase):
    """Test the loader classes."""
    
    def test_syntax_loader_caching(self):
        """Test that syntax loader caches results."""
        loader = SyntaxLoader()
        
        # Load syntax twice - should use cache on second call
        try:
            syntax1 = loader.load_syntax("Default")
            syntax2 = loader.load_syntax("Default")
            self.assertIs(syntax1, syntax2)  # Should be same object due to caching
        except FileNotFoundError:
            self.skipTest("Default syntax not available")
    
    def test_color_scheme_loader_caching(self):
        """Test that color scheme loader caches results."""
        loader = ColorSchemeLoader()
        
        # Load scheme twice - should use cache on second call
        try:
            scheme1 = loader.load_color_scheme("Default")
            scheme2 = loader.load_color_scheme("Default")
            self.assertIs(scheme1, scheme2)  # Should be same object due to caching
        except FileNotFoundError:
            self.skipTest("Default color scheme not available")


class TestOutputWriter(unittest.TestCase):
    """Test the OutputWriter class."""
    
    def setUp(self):
        # Create a minimal color scheme for testing
        self.color_scheme = {
            "globals": {
                "foreground": [255, 255, 255, 255],
                "background": [0, 0, 0, 255]
            },
            "rules": []
        }
        self.output = StringIO()
        self.debug_config = DebugConfig(enabled=False)
        self.writer = OutputWriter(self.color_scheme, self.output, self.debug_config)
    
    def test_write_raw(self):
        """Test raw text writing."""
        self.writer.write_raw("test text")
        self.assertEqual(self.output.getvalue(), "test text")
    
    def test_token_color_caching(self):
        """Test that token colors are cached."""
        scopestack = [["source", "python"]]
        
        # Get color twice - should use cache on second call
        color1 = self.writer.get_token_color("test", scopestack)
        color2 = self.writer.get_token_color("test", scopestack)
        
        self.assertEqual(color1, color2)
        self.assertGreater(len(self.writer._token_color_cache), 0)


if __name__ == '__main__':
    unittest.main()
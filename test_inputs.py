#!/usr/bin/env python3
"""
Test inputs to capture current behavior before and after modernization.
"""

# Test cases with different languages and scenarios
TEST_CASES = [
    {
        "name": "python_basic",
        "content": "print('hello world')\nif True:\n    x = 42",
        "syntax": "Python",
        "color_scheme": "Default"
    },
    {
        "name": "javascript_basic", 
        "content": "function hello() {\n    console.log('Hello');\n    return 42;\n}",
        "syntax": "JavaScript",
        "color_scheme": "Default"
    },
    {
        "name": "c_basic",
        "content": "#include <stdio.h>\nint main() {\n    printf(\"Hello\\n\");\n    return 0;\n}",
        "syntax": "C",
        "color_scheme": "Default"
    },
    {
        "name": "json_basic",
        "content": '{\n    "name": "test",\n    "value": 123,\n    "active": true\n}',
        "syntax": "JSON", 
        "color_scheme": "Default"
    },
    {
        "name": "auto_detect_python",
        "content": "#!/usr/bin/env python3\nprint('auto detected')",
        "syntax": None,  # Auto-detect from shebang
        "color_scheme": "Default"
    }
]
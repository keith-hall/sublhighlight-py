#!/usr/bin/env python3
"""
Test current behavior against baseline to verify regression.
"""

import subprocess
import tempfile
import os
import json
from test_inputs import TEST_CASES

def capture_output(content, syntax=None, color_scheme="Default", show_scopes=False):
    """Run hl.py with given input and capture output."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        f.flush()
        
        cmd = ['python3', 'hl.py']
        if syntax:
            cmd.extend(['-s', syntax])
        cmd.extend(['-c', color_scheme])
        if show_scopes:
            cmd.append('-S')
        cmd.append(f.name)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd='.')
            return {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        finally:
            os.unlink(f.name)

def capture_stdin_output(content, syntax=None, color_scheme="Default"):
    """Run hl.py with stdin input and capture output."""
    cmd = ['python3', 'hl.py']
    if syntax:
        cmd.extend(['-s', syntax])
    cmd.extend(['-c', color_scheme])
    
    result = subprocess.run(cmd, input=content, capture_output=True, text=True, cwd='.')
    return {
        'stdout': result.stdout,
        'stderr': result.stderr,
        'returncode': result.returncode
    }

def test_current_behavior():
    """Test current behavior against baseline."""
    # Load baseline
    with open('/tmp/baseline_behavior.json', 'r') as f:
        baseline = json.load(f)
    
    errors = []
    
    for test_case in TEST_CASES:
        name = test_case['name']
        content = test_case['content']
        syntax = test_case['syntax']
        color_scheme = test_case['color_scheme']
        
        print(f"Testing: {name}")
        
        # Test with file input
        result_file = capture_output(content, syntax, color_scheme)
        baseline_file = baseline[name]['file_input']
        
        if result_file['stdout'] != baseline_file['stdout']:
            errors.append(f"{name} (file): stdout differs")
        if result_file['returncode'] != baseline_file['returncode']:
            errors.append(f"{name} (file): returncode differs")
        
        # Test with stdin input
        result_stdin = capture_stdin_output(content, syntax, color_scheme)
        baseline_stdin = baseline[name]['stdin_input']
        
        if result_stdin['stdout'] != baseline_stdin['stdout']:
            errors.append(f"{name} (stdin): stdout differs")
        if result_stdin['returncode'] != baseline_stdin['returncode']:
            errors.append(f"{name} (stdin): returncode differs")
    
    if errors:
        print("REGRESSION DETECTED:")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("All tests passed - no regression detected!")
        return True

if __name__ == '__main__':
    success = test_current_behavior()
    exit(0 if success else 1)
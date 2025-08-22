#!/usr/bin/env python3
"""
Capture current behavior for regression testing during modernization.
"""

import subprocess
import tempfile
import os
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

def save_current_behavior():
    """Capture and save current behavior for all test cases."""
    results = {}
    
    for test_case in TEST_CASES:
        name = test_case['name']
        content = test_case['content']
        syntax = test_case['syntax']
        color_scheme = test_case['color_scheme']
        
        print(f"Capturing: {name}")
        
        # Test with file input
        result_file = capture_output(content, syntax, color_scheme)
        
        # Test with stdin input (for auto-detection cases)
        result_stdin = capture_stdin_output(content, syntax, color_scheme)
        
        results[name] = {
            'file_input': result_file,
            'stdin_input': result_stdin,
            'test_case': test_case
        }
    
    # Save results
    import json
    with open('/tmp/baseline_behavior.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Baseline behavior saved to /tmp/baseline_behavior.json")
    return results

if __name__ == '__main__':
    save_current_behavior()
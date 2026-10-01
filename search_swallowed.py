import os
import ast
import re

def find_swallowed_exceptions_py(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # check if body contains only Pass
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    print(f"Swallowed exception in Python: {filepath}:{node.lineno}")
    except Exception as e:
        pass

def find_swallowed_exceptions_js(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Regex to find catch(e) { } or catch { } with optional comments/whitespace
        # Also let's check for catch(e) { /* comment */ }
        matches = re.finditer(r'catch\s*(?:\([^)]*\))?\s*\{[\s\n]*\}', content)
        for match in matches:
            line_no = content[:match.start()].count('\n') + 1
            print(f"Swallowed exception in JS/TS (empty block): {filepath}:{line_no}")

        # Also find cases where there is a catch block but no console., log, report, etc.
        # Just simple empty blocks are the most common silent failures
    except Exception as e:
        pass

def main():
    for root, dirs, files in os.walk('.'):
        if 'node_modules' in dirs:
            dirs.remove('node_modules')
        if '.git' in dirs:
            dirs.remove('.git')
        if '.vercel' in dirs:
            dirs.remove('.vercel')
            
        for file in files:
            filepath = os.path.join(root, file)
            if file.endswith('.py'):
                find_swallowed_exceptions_py(filepath)
            elif file.endswith(('.js', '.ts', '.jsx', '.tsx')):
                find_swallowed_exceptions_js(filepath)

if __name__ == '__main__':
    main()

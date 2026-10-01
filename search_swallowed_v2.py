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
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    print(f"Python: {filepath}:{node.lineno}")
    except Exception as e:
        pass

def find_swallowed_exceptions_js(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        # Find empty catch blocks, even if they have spaces, newlines, or comments
        # this regex is basic but can match catch(e) { } and catch { /* ignored */ }
        matches = re.finditer(r'catch\s*(?:\([^)]*\))?\s*\{\s*(?:\/\*[\s\S]*?\*\/\s*|\/\/.*?\s*)*\}', content)
        for match in matches:
            line_no = content[:match.start()].count('\n') + 1
            print(f"JS/TS: {filepath}:{line_no}")
    except Exception as e:
        pass

def main():
    for root, dirs, files in os.walk('.'):
        for ignore_dir in ['node_modules', '.git', '.vercel', 'dist', 'build']:
            if ignore_dir in dirs:
                dirs.remove(ignore_dir)
            
        for file in files:
            filepath = os.path.join(root, file)
            if file.endswith('.py'):
                find_swallowed_exceptions_py(filepath)
            elif file.endswith(('.js', '.ts', '.jsx', '.tsx')):
                find_swallowed_exceptions_js(filepath)

if __name__ == '__main__':
    main()

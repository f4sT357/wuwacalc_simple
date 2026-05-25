import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def is_name_check_if(node):
    # Detect pattern: if __name__ == '__main__'
    if not isinstance(node, ast.If):
        return False
    test = node.test
    # look for comparison: Name('__name__') == Constant('__main__')
    if isinstance(test, ast.Compare):
        left = test.left
        comparators = test.comparators
        if isinstance(left, ast.Name) and left.id == '__name__':
            for comp in comparators:
                if isinstance(comp, ast.Constant) and comp.value == '__main__':
                    return True
    return False


def analyze_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    try:
        tree = ast.parse(src, filename=path)
    except Exception as e:
        return {'error': str(e)}

    top_level_calls = []
    for node in tree.body:
        # Skip imports, classdefs, funcdefs
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Skip if blocks that check __name__
        if is_name_check_if(node):
            continue
        # If a simple Expr whose value is a Call -> side-effect likely
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            # capture code snippet
            lineno = node.lineno
            call_code = ast.get_source_segment(src, node) or ''
            top_level_calls.append((lineno, call_code.strip()))
        # Assignment where value is Call
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            lineno = node.lineno
            code = ast.get_source_segment(src, node) or ''
            top_level_calls.append((lineno, code.strip()))
        # AugAssign or other nodes that might include calls
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.BinOp):
            # ignore
            pass
    return {'calls': top_level_calls}


def main():
    results = {}
    for fname in os.listdir(ROOT):
        if not fname.endswith('.py'):
            continue
        if fname == os.path.basename(__file__):
            continue
        path = os.path.join(ROOT, fname)
        results[fname] = analyze_file(path)

    for fname, info in sorted(results.items()):
        if 'error' in info:
            print(fname, 'PARSE ERROR:', info['error'])
            continue
        if info['calls']:
            print(f"{fname}: Found {len(info['calls'])} top-level call(s):")
            for lineno, code in info['calls']:
                print(f"  L{lineno}: {code}")

if __name__ == '__main__':
    main()

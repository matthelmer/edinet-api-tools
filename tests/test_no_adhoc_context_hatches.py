"""Drift guard: ad-hoc context-matching hatches must not reappear (0.8.0).

Before the tier migration, securities.py carried five hand-rolled
custom-namespace hatches — loops over match_element_by_suffix output
comparing コンテキストID against a period. Those are now declared
suffix-tiers resolved inside extraction.py, and the baseline outside
extraction.py is ZERO. This AST guard fails on any new hatch written in
the house idiom, wherever it lands in the package:

(i)  any call to match_element_by_suffix outside parsers/extraction.py;
(ii) any equality comparison (== / !=) against コンテキストID inside a
     for/while loop outside parsers/extraction.py — whether the literal
     appears in the comparison itself or via a name assigned from an
     expression containing it (ctx = row.get('コンテキストID'); ctx == p).

Membership tests ('Member' in ctx), regex searches, and plain reads of the
column are legitimate (segments/_dimensional/large_holding parse context
STRUCTURE, they don't waterfall on period equality) and do not trip the
guard. New hatches belong in tier tables: Tier(..., suffix_match=True).
"""
import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parent.parent / 'edinet_tools'
ALLOWED = {PACKAGE_ROOT / 'parsers' / 'extraction.py'}

CTX_LITERAL = 'コンテキストID'


def _called_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ''


def _subtree_has_ctx_literal(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Constant) and n.value == CTX_LITERAL
               for n in ast.walk(node))


def _tainted_names(tree: ast.AST) -> set:
    """Names assigned anywhere in the module from an expression containing
    the コンテキストID literal (module-level taint is deliberately coarse —
    this is a guard, not a dataflow analysis)."""
    tainted = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.value is not None \
                and _subtree_has_ctx_literal(node.value):
            for target in node.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        tainted.add(name.id)
    return tainted


def _violations_in(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    tainted = _tainted_names(tree)
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and \
                _called_name(node) == 'match_element_by_suffix':
            violations.append(
                f'{path.name}:{node.lineno}: match_element_by_suffix call '
                f'outside extraction.py — declare a suffix tier instead')
        if isinstance(node, (ast.For, ast.While)):
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Compare):
                    continue
                if not any(isinstance(op, (ast.Eq, ast.NotEq))
                           for op in sub.ops):
                    continue
                sides = [sub.left, *sub.comparators]
                hit = any(
                    _subtree_has_ctx_literal(side)
                    or (isinstance(side, ast.Name) and side.id in tainted)
                    for side in sides
                )
                if hit:
                    violations.append(
                        f'{path.name}:{sub.lineno}: コンテキストID equality '
                        f'inside a loop outside extraction.py — declare a '
                        f'suffix tier instead')
    return violations


def test_no_adhoc_context_hatches_outside_extraction():
    violations = []
    for path in sorted(PACKAGE_ROOT.rglob('*.py')):
        if path in ALLOWED:
            continue
        violations.extend(_violations_in(path))
    assert violations == [], (
        'Ad-hoc context hatch(es) found — the baseline is ZERO after the '
        'tier migration:\n' + '\n'.join(violations))


def test_guard_catches_the_house_idiom():
    """Self-test: the guard must flag both hatch shapes it exists for."""
    direct = ast.parse(
        "def hatch(csv_files, period):\n"
        "    for row in match_element_by_suffix(csv_files, 'X'):\n"
        "        if (row.get('コンテキストID', '') or '') == period:\n"
        "            return row\n")
    tainted_form = ast.parse(
        "def hatch2(rows, period):\n"
        "    ctx = row.get('コンテキストID', '')\n"
        "    for row in rows:\n"
        "        if ctx != period:\n"
        "            continue\n")
    import tempfile, os
    for tree_src in (direct, tainted_form):
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(ast.unparse(tree_src))
            tmp = fh.name
        try:
            assert _violations_in(Path(tmp)) != []
        finally:
            os.unlink(tmp)

import ast
import sys
from pathlib import Path

BOOTSTRAP = Path(__file__).resolve().parents[2] / "bootstrap"


def _imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_bootstrap_imports_only_stdlib():
    files = sorted(BOOTSTRAP.glob("*.py"))
    assert files
    for f in files:
        bad = {
            r for r in _imported_roots(f) if r not in sys.stdlib_module_names and r != "bootstrap"
        }
        assert not bad, f"{f.name} imports non-stdlib modules: {bad}"

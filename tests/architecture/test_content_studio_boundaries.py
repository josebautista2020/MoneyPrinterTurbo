"""Architecture gates for Content Studio AI."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = REPO_ROOT / "extensions"
MPT_ADAPTER = EXTENSIONS / "mpt_adapter"
CORE = EXTENSIONS / "content_studio"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _python_files(root: Path):
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_reusable_extensions_do_not_depend_on_verticals() -> None:
    violations = []
    for path in _python_files(EXTENSIONS):
        for module in _imports(path):
            if module == "verticals" or module.startswith("verticals."):
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {module}")
    assert not violations, "Reusable extensions depend on a vertical: " + ", ".join(violations)


def test_only_mpt_adapter_imports_moneyprinterturbo_internals() -> None:
    violations = []
    for path in _python_files(EXTENSIONS):
        if MPT_ADAPTER in path.parents:
            continue
        for module in _imports(path):
            if module == "app" or module.startswith("app."):
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {module}")
    assert not violations, "Direct MPT dependency outside mpt_adapter: " + ", ".join(violations)


def test_content_studio_core_is_provider_neutral() -> None:
    forbidden_prefixes = ("app", "verticals")
    violations = []
    for path in _python_files(CORE):
        for module in _imports(path):
            if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden_prefixes):
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {module}")
    assert not violations, "Core is not provider-neutral: " + ", ".join(violations)


def test_required_rendering_contracts_exist() -> None:
    rendering_file = CORE / "rendering.py"
    tree = ast.parse(rendering_file.read_text(encoding="utf-8"))
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert {"RenderingEngine", "ExecutionRequest", "ExecutionResult"} <= classes


def test_mpt_adapter_is_the_explicit_mpt_boundary() -> None:
    adapter_file = MPT_ADAPTER / "adapter.py"
    modules = _imports(adapter_file)
    assert any(module == "app" or module.startswith("app.") for module in modules)

"""Architecture tests for the deterministic engine boundary."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORTS = {"anthropic", "httpx", "openai", "requests", "socket"}
PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "unihive"


def imported_root_names(path: Path) -> set[str]:
    """Return the top-level package names imported by one Python module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module.partition(".")[0])
    return names


def test_network_and_llm_imports_are_confined_to_llm_package() -> None:
    """Only src/unihive/llm may import network or LLM client packages."""
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative_path = path.relative_to(PACKAGE_ROOT)
        if relative_path.parts and relative_path.parts[0] == "llm":
            continue

        forbidden = imported_root_names(path) & FORBIDDEN_IMPORTS
        if forbidden:
            imports = ", ".join(sorted(forbidden))
            violations.append(f"{relative_path.as_posix()}: {imports}")

    assert not violations, "Forbidden imports outside unihive/llm:\n" + "\n".join(
        violations
    )


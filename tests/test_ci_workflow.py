from __future__ import annotations

from pathlib import Path


def test_ci_workflow_runs_project_quality_gates() -> None:
    workflow_path = Path(".github/workflows/ci.yml")

    assert workflow_path.exists()

    workflow = workflow_path.read_text(encoding="utf-8")
    expected_snippets = [
        "name: CI",
        "pull_request:",
        "push:",
        "lint:",
        "type-check:",
        "dependency-check:",
        "test:",
        "build:",
        "needs: [lint, type-check, dependency-check, test]",
        "python-version: [\"3.11\", \"3.12\", \"3.13\", \"3.14\"]",
        "uv run ruff check .",
        "uv run mypy wordstat_mcp",
        "uv run deptry .",
        "uv run pytest",
        "uv build",
    ]

    for snippet in expected_snippets:
        assert snippet in workflow

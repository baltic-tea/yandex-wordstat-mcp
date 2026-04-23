from __future__ import annotations

import tomllib
from pathlib import Path


def test_mypy_uses_pydantic_plugin() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    mypy_config = pyproject["tool"]["mypy"]
    pydantic_mypy_config = pyproject["tool"]["pydantic-mypy"]

    assert "pydantic.mypy" in mypy_config["plugins"]
    assert pydantic_mypy_config["init_typed"] is True

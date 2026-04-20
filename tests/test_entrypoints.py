from __future__ import annotations

import importlib
import logging
import runpy
import sys

import pytest

from wordstat_mcp import __all__ as package_all
from wordstat_mcp.exceptions import WordstatConfigError


def test_package_exports_mcp() -> None:
    assert package_all == ["mcp"]


def test_main_configures_logging_validates_settings_and_runs_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"logging": None, "settings_calls": 0, "run_calls": 0}
    module = importlib.import_module("wordstat_mcp.__main__")

    monkeypatch.setattr(
        module.logging,
        "basicConfig",
        lambda **kwargs: state.__setitem__("logging", kwargs),
    )
    monkeypatch.setattr(
        module,
        "WordstatSettings",
        lambda: (
            state.__setitem__("settings_calls", state["settings_calls"] + 1) or object()
        ),
    )
    monkeypatch.setattr(
        module.mcp,
        "run",
        lambda: state.__setitem__("run_calls", state["run_calls"] + 1),
    )

    module.main()

    assert state["logging"] == {
        "level": logging.INFO,
        "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
    }
    assert state["settings_calls"] == 1
    assert state["run_calls"] == 1


def test_main_raises_on_invalid_settings_before_running_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("wordstat_mcp.__main__")
    monkeypatch.setattr(module.logging, "basicConfig", lambda **_: None)
    monkeypatch.setattr(
        module,
        "WordstatSettings",
        lambda: (_ for _ in ()).throw(WordstatConfigError("required")),
    )
    monkeypatch.setattr(
        module.mcp,
        "run",
        lambda: pytest.fail("mcp.run should not execute when settings fail"),
    )

    with pytest.raises(WordstatConfigError, match="required"):
        module.main()


def test_module_execution_runs_main(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"settings_calls": 0, "run_calls": 0}
    monkeypatch.setattr(
        "wordstat_mcp.api_settings.WordstatSettings",
        lambda: (
            state.__setitem__("settings_calls", state["settings_calls"] + 1) or object()
        ),
    )
    monkeypatch.setattr(
        "wordstat_mcp.tools.mcp.run",
        lambda: state.__setitem__("run_calls", state["run_calls"] + 1),
    )
    sys.modules.pop("wordstat_mcp.__main__", None)

    runpy.run_module("wordstat_mcp.__main__", run_name="__main__")

    assert state["settings_calls"] == 1
    assert state["run_calls"] == 1

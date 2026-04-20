from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.exceptions import WordstatConfigError


def test_settings_require_folder_id() -> None:
    with pytest.raises(ValidationError, match="folder_id"):
        WordstatSettings(folder_id="", api_key="secret")


def test_settings_accept_empty_string_credentials_values() -> None:
    settings = WordstatSettings(folder_id="folder", api_key="", iam_token="")
    with pytest.raises(WordstatConfigError, match="API key or IAM token is required"):
        _ = settings.headers


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("max_attempts", 0),
        ("max_concurrency", 0),
        ("backoff_seconds", -0.1),
        ("max_backoff_seconds", -0.1),
    ],
)
def test_settings_validate_numeric_limits(
    field_name: str, value: int | float
) -> None:
    kwargs = {"folder_id": "folder", "api_key": "secret", field_name: value}
    with pytest.raises(ValidationError, match=field_name):
        WordstatSettings(**kwargs)


def test_settings_headers_use_api_key() -> None:
    settings = WordstatSettings(folder_id="folder", api_key="secret")
    assert settings.headers == {
        "Accept": "application/json",
        "Authorization": "Api-Key secret",
        "Content-Type": "application/json",
    }


def test_settings_headers_prefer_iam_token() -> None:
    settings = WordstatSettings(
        folder_id="folder",
        api_key="secret",
        iam_token="iam-token",
    )
    assert settings.headers["Authorization"] == "Bearer iam-token"


def test_settings_use_stabilized_backoff_defaults() -> None:
    settings = WordstatSettings(folder_id="folder", api_key="secret")

    assert settings.backoff_seconds == 0.5
    assert settings.max_backoff_seconds == 8.0


def test_settings_normalize_api_url_with_path_to_trailing_slash() -> None:
    settings = WordstatSettings(
        folder_id="folder",
        api_key="secret",
        api_url="https://searchapi.api.cloud.yandex.net/v2/wordstat",
    )

    assert str(settings.api_url).endswith("/v2/wordstat/")


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORDSTAT_FOLDER_ID", "folder-from-env")
    monkeypatch.setenv("WORDSTAT_API_KEY", "api-key-from-env")
    monkeypatch.setenv("WORDSTAT_IAM_TOKEN", "iam-token-from-env")

    settings = WordstatSettings()

    assert settings.folder_id == "folder-from-env"
    assert isinstance(settings.api_key, SecretStr)
    assert settings.api_key.get_secret_value() == "api-key-from-env"
    assert isinstance(settings.iam_token, SecretStr)
    assert settings.iam_token.get_secret_value() == "iam-token-from-env"


def test_update_iam_token_returns_new_instance() -> None:
    settings = WordstatSettings(folder_id="folder", api_key="secret")

    updated = settings.update_iam_token("new-token")

    assert updated is not settings
    assert isinstance(updated.iam_token, SecretStr)
    assert updated.iam_token.get_secret_value() == "new-token"
    assert settings.iam_token is None

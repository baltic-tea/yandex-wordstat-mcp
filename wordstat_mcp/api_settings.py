from __future__ import annotations

from typing import Self

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    AnyHttpUrl,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from wordstat_mcp.exceptions import WordstatConfigError


class WordstatSettings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        frozen=True,
        case_sensitive=False,
        str_strip_whitespace=True,
        env_prefix="WORDSTAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    folder_id: str = Field(min_length=1)
    iam_token: SecretStr | None = Field(default=None)
    api_key: SecretStr | None = Field(default=None)
    api_http_url: AnyHttpUrl | str = Field(
        default="https://searchapi.api.cloud.yandex.net/v2/wordstat/",
        validation_alias=AliasChoices("api_url", "base_url"),
    )
    timeout_seconds: int | float = Field(default=30, ge=0)
    backoff_seconds: int | float = Field(default=0.5, ge=0)
    max_backoff_seconds: int | float = Field(default=8.0, ge=0)
    max_attempts: int = Field(default=5, ge=1)
    max_concurrency: int = Field(default=5, ge=1)

    @field_validator("api_http_url", mode="after")
    @classmethod
    def normalize_api_url(cls, value: object) -> object:
        return url if (url := str(value)).endswith("/") else url + "/"

    @model_validator(mode="after")
    def validate_credentials(self) -> Self:
        if self.iam_token is None and self.api_key is None:
            raise WordstatConfigError(
                "WORDSTAT_IAM_TOKEN or WORDSTAT_API_KEY is required."
            )
        return self

    @property
    def headers(self) -> dict[str, str]:
        """Return request headers."""

        if self.iam_token:
            auth_str = f"Bearer {self.iam_token.get_secret_value()}"
        elif self.api_key:
            auth_str = f"Api-Key {self.api_key.get_secret_value()}"
        else:
            raise WordstatConfigError("API key or IAM token is required.")

        return {
            "Accept": "application/json",
            "Authorization": auth_str,
            "Content-Type": "application/json",
        }

    @property
    def api_url(self) -> str:
        return str(self.api_http_url)

    def update_iam_token(self, new_token: str | SecretStr) -> WordstatSettings:
        if isinstance(new_token, str):
            new_token = SecretStr(new_token)
        return self.model_copy(update={"iam_token": new_token}, deep=True)

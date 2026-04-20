from __future__ import annotations

from typing import Any


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        body: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeSession:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.response = response or FakeResponse()
        self.closed = False
        self.calls: list[dict[str, Any]] = []

    def post(
        self, url: str, *, headers: dict[str, str], json: dict[str, Any]
    ) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.response

    async def close(self) -> None:
        self.closed = True

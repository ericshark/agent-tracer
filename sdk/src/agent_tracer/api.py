"""Synchronous client for the Agent Tracer SDK API (`/v1/*`).

Tracing itself never goes through here — spans are exported in the background
and never raise. These calls are explicit requests made by your code
(datasets, experiments), so failures raise `ApiError`.
"""

from __future__ import annotations

from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Agent Tracer API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class ApiClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._api_key:
            raise ApiError(
                401, "no API key configured (set AGENT_TRACER_API_KEY or pass api_key=)"
            )
        response = self._client.request(
            method,
            self.base_url + path,
            headers={"Authorization": f"Bearer {self._api_key}"},
            **kwargs,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = None
            raise ApiError(response.status_code, str(detail or response.text[:500]))
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: Any) -> Any:
        return self.request("POST", path, json=body)

    def close(self) -> None:
        self._client.close()

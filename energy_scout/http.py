"""HTTP-клиент с ретраями, вежливыми паузами и режимом фикстур (для тестов/демо)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 EnergyScout/1.0"
)


class HttpClient:
    """Тонкая обёртка над httpx: паузы между запросами и повторные попытки."""

    def __init__(self, delay: float = 0.4, timeout: float = 25.0,
                 max_retries: int = 3) -> None:
        self.delay = delay
        self.max_retries = max_retries
        self._client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            },
            timeout=timeout,
            follow_redirects=True,
        )
        self._last_request_at = 0.0

    def _polite_wait(self) -> None:
        if self.delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._polite_wait()
            try:
                resp = self._client.request(method, url, **kwargs)
                self._last_request_at = time.monotonic()
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                return resp
            except (httpx.HTTPError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    break
                time.sleep(min(2 ** attempt, 10))
        raise ConnectionError(f"Запрос не удался после {self.max_retries} попыток: {url} — {last_exc}")

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post_json(self, url: str, payload: dict) -> dict:
        resp = self.request(
            "POST", url,
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        return resp.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class FixtureClient:
    """Клиент, который вместо сети отдаёт сохранённые фикстуры (демо и тесты)."""

    def __init__(self, fixtures_dir: str | Path) -> None:
        self.fixtures_dir = Path(fixtures_dir)
        self.calls: list[tuple[str, str]] = []

    def _load(self, key: str) -> str:
        path = self.fixtures_dir / key
        if not path.exists():
            raise FileNotFoundError(f"Нет фикстуры {key}")
        return path.read_text(encoding="utf-8")

    def get(self, url: str, **kwargs: Any) -> "FixtureResponse":
        self.calls.append(("GET", url))
        key = url.split("?", 1)[0].rstrip("/").split("://")[-1].replace("/", "_")
        return FixtureResponse(self._load(f"{key}.txt"))

    def post_json(self, url: str, payload: dict) -> dict:
        self.calls.append(("POST", url))
        operation = self._operation(payload)
        return json.loads(self._load(f"dina_graph_{operation}.json"))

    @staticmethod
    def _operation(payload: dict) -> str:
        query = payload.get("query", "")
        # ВАЖНО: products-запрос содержит поле categories, поэтому проверяем
        # его раньше, чем categories.
        if "products" in query:
            variables = payload.get("variables", {})
            page = variables.get("_page") or variables.get("page") or 1
            return f"products_p{page}"
        if "shops" in query:
            return "shops"
        if "categories" in query:
            return "categories"
        return "unknown"

    def close(self) -> None:
        pass

    def __enter__(self) -> "FixtureClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class FixtureResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

"""The one place the app talks to an LLM.

Everything else depends on the LLMClient protocol, so the provider can be swapped
(spec section 8) without touching ingestion or query code.
"""

import json
import logging
import time
from collections.abc import Iterator
from typing import Any, Protocol

import httpx

from app.config import get_settings

log = logging.getLogger("recall.llm")


class LLMError(RuntimeError):
    """`retryable` is True for rate limits, server errors and timeouts: worth trying again later."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class LLMClient(Protocol):
    def generate(
        self, prompt: str, *, system: str | None = None, json_schema: dict | None = None
    ) -> str: ...

    def stream(self, prompt: str, *, system: str | None = None) -> Iterator[str]: ...


class GeminiClient:
    """Calls the Gemini REST API. The key comes from GEMINI_API_KEY, never from code.

    `models` are tried in order: when one is rate-limited or overloaded (429, 5xx, timeout),
    the next one gets the request, so a busy free-tier model doesn't fail the user. When all
    of them are busy, they're tried once more after a short wait: free-tier overloads are
    usually over within seconds.
    """

    base_url = "https://generativelanguage.googleapis.com/v1beta"
    ROUNDS = 2
    WAIT_S = 2.0

    def __init__(self, api_key: str, models: list[str], timeout: float = 30.0):
        if not models:
            raise ValueError("at least one model is needed")
        self._models = models
        self._http = httpx.Client(timeout=timeout, headers={"x-goog-api-key": api_key})

    def _attempts(self):
        """(model, is the last attempt) in order: every model, then every model again."""
        tries = [(r, m) for r in range(self.ROUNDS) for m in self._models]
        for n, (round_, model) in enumerate(tries):
            if n and round_ != tries[n - 1][0]:
                log.warning("every model is busy; waiting %.0fs and trying again", self.WAIT_S)
                time.sleep(self.WAIT_S)
            yield model, n == len(tries) - 1

    def generate(
        self, prompt: str, *, system: str | None = None, json_schema: dict | None = None
    ) -> str:
        body = self._body(prompt, system, json_schema)
        for model, last in self._attempts():
            try:
                resp = self._http.post(f"{self.base_url}/models/{model}:generateContent", json=body)
                self._raise_for_status(resp.status_code, resp.text)
            except (httpx.TransportError, LLMError) as exc:
                err = _as_llm_error(exc)
                if err.retryable and not last:
                    log.warning("%s unavailable (%s)", model, err)
                    continue
                raise err from exc
            text = _text_of(resp.json())
            if not text:
                raise LLMError("Gemini returned no text (the response may have been blocked)")
            return text
        raise AssertionError("unreachable")

    def stream(self, prompt: str, *, system: str | None = None) -> Iterator[str]:
        body = self._body(prompt, system, None)
        for model, last in self._attempts():
            url = f"{self.base_url}/models/{model}:streamGenerateContent?alt=sse"
            started = False
            try:
                with self._http.stream("POST", url, json=body) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        self._raise_for_status(resp.status_code, resp.text)
                    for line in resp.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        text = _text_of(json.loads(line[5:]))
                        if text:
                            started = True
                            yield text
                return
            except (httpx.TransportError, LLMError) as exc:
                err = _as_llm_error(exc)
                # Once text has reached the user, switching models would garble the answer.
                if err.retryable and not started and not last:
                    log.warning("%s unavailable (%s)", model, err)
                    continue
                raise err from exc

    def _body(self, prompt: str, system: str | None, json_schema: dict | None) -> dict[str, Any]:
        body: dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        config: dict[str, Any] = {"temperature": 0.2}
        if json_schema is not None:
            config["responseMimeType"] = "application/json"
            config["responseSchema"] = json_schema
        body["generationConfig"] = config
        return body

    @staticmethod
    def _raise_for_status(status: int, text: str) -> None:
        if status == 200:
            return
        log.info("Gemini returned %s: %s", status, text[:300])
        # What people see is the message; the provider's details go to the log.
        if status == 429:
            raise LLMError(BUSY + " (it's limiting how often it can be asked)", retryable=True)
        if status >= 500:
            raise LLMError(BUSY, retryable=True)
        raise LLMError(f"Gemini refused the request ({status}).")


BUSY = "Gemini, the AI behind answers, is busy right now. Try again in a moment"


def _as_llm_error(exc: Exception) -> LLMError:
    if isinstance(exc, LLMError):
        return exc
    log.info("couldn't reach Gemini: %s", exc or type(exc).__name__)
    return LLMError(BUSY, retryable=True)


def _text_of(payload: dict) -> str:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        return ""
    # Skip the model's thought summaries, if any; only the answer text is wanted.
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


DAY_IS_OVER = (
    "The demo has used today's answers from Gemini, the AI behind them; they're back tomorrow. "
    "Searching, reading and reviewing still work"
)


class DailyCap:
    """Wraps a client so that no more than `cap` calls a day (UTC) are made, across every
    process: the count is kept in Postgres. Keeps a public demo inside the free tier."""

    def __init__(self, inner: LLMClient, cap: int):
        self._inner = inner
        self._cap = cap

    def _count(self) -> None:
        from sqlalchemy import text

        from app.db import engine

        with engine.begin() as conn:
            calls = conn.scalar(
                text(
                    "INSERT INTO llm_calls (day, calls) "
                    "VALUES ((now() AT TIME ZONE 'utc')::date, 1) ON CONFLICT (day) "
                    "DO UPDATE SET calls = llm_calls.calls + 1 RETURNING calls"
                )
            )
        if calls > self._cap:
            raise LLMError(DAY_IS_OVER)

    def generate(
        self, prompt: str, *, system: str | None = None, json_schema: dict | None = None
    ) -> str:
        self._count()
        return self._inner.generate(prompt, system=system, json_schema=json_schema)

    def stream(self, prompt: str, *, system: str | None = None) -> Iterator[str]:
        self._count()
        yield from self._inner.stream(prompt, system=system)


def get_llm() -> LLMClient:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY is not set. Add it to backend/.env and reprocess the item.")
    models = [settings.gemini_model, *settings.gemini_fallback_models]
    client: LLMClient = GeminiClient(settings.gemini_api_key, models)
    if settings.daily_llm_calls > 0:
        client = DailyCap(client, settings.daily_llm_calls)
    return client

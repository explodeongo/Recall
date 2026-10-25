"""The one place the app talks to an LLM.

Everything else depends on the LLMClient protocol, so the provider can be swapped
(spec section 8) without touching ingestion or query code.
"""

import json
import logging
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
    the next one gets the request, so a busy free-tier model doesn't fail the user.
    """

    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, models: list[str], timeout: float = 30.0):
        if not models:
            raise ValueError("at least one model is needed")
        self._models = models
        self._http = httpx.Client(timeout=timeout, headers={"x-goog-api-key": api_key})

    def generate(
        self, prompt: str, *, system: str | None = None, json_schema: dict | None = None
    ) -> str:
        body = self._body(prompt, system, json_schema)
        for i, model in enumerate(self._models):
            try:
                resp = self._http.post(f"{self.base_url}/models/{model}:generateContent", json=body)
                self._raise_for_status(resp.status_code, resp.text)
            except (httpx.TransportError, LLMError) as exc:
                err = _as_llm_error(exc)
                if err.retryable and i + 1 < len(self._models):
                    log.warning("%s unavailable (%s); trying %s", model, err, self._models[i + 1])
                    continue
                raise err from exc
            text = _text_of(resp.json())
            if not text:
                raise LLMError("Gemini returned no text (the response may have been blocked)")
            return text
        raise AssertionError("unreachable")

    def stream(self, prompt: str, *, system: str | None = None) -> Iterator[str]:
        body = self._body(prompt, system, None)
        for i, model in enumerate(self._models):
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
                if err.retryable and not started and i + 1 < len(self._models):
                    log.warning("%s unavailable (%s); trying %s", model, err, self._models[i + 1])
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
        retryable = status == 429 or status >= 500
        raise LLMError(f"Gemini returned {status}: {text[:300]}", retryable=retryable)


def _as_llm_error(exc: Exception) -> LLMError:
    if isinstance(exc, LLMError):
        return exc
    return LLMError(f"Couldn't reach Gemini: {exc or type(exc).__name__}", retryable=True)


def _text_of(payload: dict) -> str:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        return ""
    # Skip the model's thought summaries, if any; only the answer text is wanted.
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def get_llm() -> LLMClient:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY is not set. Add it to backend/.env and reprocess the item.")
    models = [settings.gemini_model, *settings.gemini_fallback_models]
    return GeminiClient(settings.gemini_api_key, models)

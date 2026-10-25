"""The one place the app talks to an LLM.

Everything else depends on the LLMClient protocol, so the provider can be swapped
(spec section 8) without touching ingestion or query code.
"""

from typing import Protocol

import httpx

from app.config import get_settings


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def generate(self, prompt: str, *, system: str | None = None) -> str: ...


class GeminiClient:
    """Calls the Gemini REST API. The key comes from GEMINI_API_KEY, never from code."""

    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0):
        self._model = model
        self._http = httpx.Client(timeout=timeout, headers={"x-goog-api-key": api_key})

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        resp = self._http.post(f"{self.base_url}/models/{self._model}:generateContent", json=body)
        if resp.status_code != 200:
            raise LLMError(f"Gemini returned {resp.status_code}: {resp.text[:200]}")
        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise LLMError("Gemini response had no text") from exc
        return "".join(p.get("text", "") for p in parts).strip()


def get_llm() -> LLMClient:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY is not set")
    return GeminiClient(settings.gemini_api_key, settings.gemini_model)

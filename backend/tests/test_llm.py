import json

import httpx
import pytest

from app.services.llm import GeminiClient, LLMError


def _client(handler, models=("primary", "backup")) -> GeminiClient:
    client = GeminiClient("test-key", list(models))
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def _reply(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_generate_sends_key_in_header_and_schema():
    seen = {}

    def handler(req):
        seen["key"] = req.headers.get("x-goog-api-key")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=_reply('{"a": 1}'))

    client = GeminiClient("test-key", ["m"])
    client._http = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"x-goog-api-key": "test-key"}
    )
    assert client.generate("hi", json_schema={"type": "OBJECT"}) == '{"a": 1}'
    assert seen["key"] == "test-key"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_falls_back_when_overloaded():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if "primary" in req.url.path:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, json=_reply("from backup"))

    assert _client(handler).generate("hi") == "from backup"
    assert len(calls) == 2


def test_client_errors_do_not_fall_back():
    def handler(req):
        return httpx.Response(400, text="bad request")

    with pytest.raises(LLMError) as err:
        _client(handler).generate("hi")
    assert not err.value.retryable


def test_last_model_failure_is_retryable():
    with pytest.raises(LLMError) as err:
        _client(lambda req: httpx.Response(429, text="quota")).generate("hi")
    assert err.value.retryable


def test_stream_parses_sse_and_skips_thoughts():
    events = [
        {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}]}}]},
        _reply("Hash indexes "),
        _reply("are fast [1]."),
    ]
    body = "".join(f"data: {json.dumps(e)}\r\n\r\n" for e in events)

    def handler(req):
        assert req.url.params["alt"] == "sse"
        return httpx.Response(200, text=body)

    assert "".join(_client(handler).stream("q")) == "Hash indexes are fast [1]."


def test_stream_falls_back_before_first_token():
    def handler(req):
        if "primary" in req.url.path:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text=f"data: {json.dumps(_reply('ok'))}\n\n")

    assert list(_client(handler).stream("q")) == ["ok"]

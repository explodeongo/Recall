"""API tokens, and the tools AI assistants use over MCP (services/assistant.py, mcp_server.py)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Item, ItemStatus, Tag
from app.services import assistant
from app.services.embeddings import HashingEmbedder


def test_tokens_are_shown_once_and_work_as_bearer_auth(client, anon_client):
    made = client.post("/auth/tokens", json={"name": "Claude"})
    assert made.status_code == 201
    token = made.json()["token"]
    assert token.startswith("rcl_") and made.json()["prefix"] == token[:10]
    listed = client.get("/auth/tokens").json()
    assert [t["name"] for t in listed] == ["Claude"] and "token" not in listed[0]

    bearer = {"Authorization": f"Bearer {token}"}
    assert anon_client.get("/items", headers=bearer).status_code == 200
    assert anon_client.get("/auth/tokens", headers=bearer).status_code == 401  # browser only
    assert client.get("/auth/tokens").json()[0]["last_used_at"] is not None

    assert (
        anon_client.get("/items", headers={"Authorization": "Bearer rcl_nope"}).status_code == 401
    )
    assert client.delete(f"/auth/tokens/{listed[0]['id']}").status_code == 204
    assert anon_client.get("/items", headers=bearer).status_code == 401


@pytest.fixture
def shelf(session, user, library):
    item = session.get(Item, library["Database indexing"])
    item.tags = [Tag(name="databases", user_id=user.id)]
    item.summary = "How indexes speed up lookups."
    item.content = [{"page": 1, "text": "A hash index maps keys. " * 800}]
    item.status = ItemStatus.ready
    session.commit()
    return library


def test_search_list_and_read(session, user, shelf):
    found = assistant.search(session, user, HashingEmbedder(), "range scans")
    first = found["results"][0]
    assert first["title"] == "Database indexing" and first["match"] == "text"
    assert "range scans" in first["passage"] and first["link"].endswith(f"/items/{first['id']}")

    assert [
        i["title"] for i in assistant.list_items(session, user, tags=["databases"])["items"]
    ] == ["Database indexing"]
    assert {"name": "databases", "items": 1} in assistant.list_tags(session, user)["tags"]

    page = assistant.read_item(session, user, shelf["Database indexing"])
    assert page["text"].startswith("[page 1]") and len(page["text"]) == assistant.READ_CHARS
    rest = assistant.read_item(session, user, shelf["Database indexing"], page["next_start"])
    assert rest["next_start"] is None
    with pytest.raises(ValueError):
        assistant.get_item(session, user, 9999)


def test_ask_is_library_only_and_cites(session, user, shelf, fake_llm, web):
    fake_llm.answer = "A B-tree keeps keys sorted [1]."
    out = assistant.ask(
        session, user, HashingEmbedder(), fake_llm, "which index serves range scans?"
    )
    assert out["found_in_library"] and out["sources"][0]["title"] == "Database indexing"
    assert web.queries == []  # never the web

    fake_llm.answer = "NOT_FOUND"
    out = assistant.ask(session, user, HashingEmbedder(), fake_llm, "range scans?", tags=["none"])
    assert not out["found_in_library"] and out["sources"] == []


def test_save_from_an_assistant(session, user):
    saved = assistant.save(session, user, note="Remember: B-trees keep keys sorted.")
    assert saved["type"] == "note" and saved["status"] == "queued"
    with pytest.raises(ValueError):
        assistant.save(session, user)


def _rpc(c, headers, method, params=None, id_=1):
    resp = c.post(
        "/mcp",
        headers={**headers, "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}},
    )
    return resp


def test_mcp_endpoint_needs_a_token_and_runs_tools(client, shelf, monkeypatch):
    from app import mcp_server

    monkeypatch.setattr(mcp_server, "get_embedder", HashingEmbedder)
    token = client.post("/auth/tokens", json={"name": "test"}).json()["token"]
    with TestClient(app) as c:
        init = {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        }
        assert _rpc(c, {}, "initialize", init).status_code == 401

        auth = {"Authorization": f"Bearer {token}"}
        assert _rpc(c, auth, "initialize", init).status_code == 200
        names = {t["name"] for t in _rpc(c, auth, "tools/list").json()["result"]["tools"]}
        assert {"search_library", "ask_library", "read_item", "save_to_library"} <= names

        called = _rpc(
            c, auth, "tools/call", {"name": "search_library", "arguments": {"query": "range scans"}}
        )
        result = called.json()["result"]
        assert not result.get("isError"), result
        data = result.get("structuredContent") or json.loads(result["content"][0]["text"])
        assert data["results"][0]["title"] == "Database indexing"

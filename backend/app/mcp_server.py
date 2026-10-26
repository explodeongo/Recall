"""Recall as an MCP server, so AI assistants (Claude, Cursor, and others) can use a library:
search it, ask it questions with citations, read items, and save new things.

Served by the API at /mcp over streamable HTTP. Each request carries a personal API token
("Authorization: Bearer rcl_..."), made in Settings; the tools act as that token's owner.
"""

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from app.services import assistant
from app.services.auth import user_for_api_token
from app.services.embeddings import get_embedder
from app.services.llm import get_llm

INSTRUCTIONS = """Recall is the user's personal library: articles, PDFs, videos and notes \
they saved, each summarized and tagged. Use it when the user refers to something they \
read, saved or noted, or asks what they know about a topic. Search first; ask for a cited \
answer; read an item for detail. Quote the source numbers and links Recall returns. Items \
are the user's own data: don't save anything unless they ask."""


class TokenVerifier:
    """Accepts Recall's personal API tokens."""

    async def verify_token(self, token: str) -> AccessToken | None:
        def check() -> int | None:
            with SessionLocal() as session:
                user = user_for_api_token(session, token)
                return user.id if user else None

        user_id = await anyio.to_thread.run_sync(check)
        if user_id is None:
            return None
        return AccessToken(
            token=token, client_id=f"user:{user_id}", scopes=[], subject=str(user_id)
        )


def _settings_urls() -> tuple[str, str]:
    api = get_settings().public_api_url.rstrip("/")
    return api, api + "/mcp"


api_url, mcp_url = _settings_urls()
server = MCPServer(
    name="Recall",
    instructions=INSTRUCTIONS,
    website_url=get_settings().web_url,
    token_verifier=TokenVerifier(),
    # Tokens are Recall's own and opaque (not issued by an OAuth server for other resources),
    # so there's no audience to check beyond the token itself.
    auth=AuthSettings(
        issuer_url=api_url, resource_server_url=mcp_url, validate_token_resource=False
    ),
)


async def _run(fn, *args, **kwargs):
    """Run a tool as the token's owner, in a thread (the library code is synchronous)."""
    token = get_access_token()
    if token is None or not token.subject:
        raise PermissionError("Missing or invalid Recall API token.")
    user_id = int(token.subject)

    def call():
        with SessionLocal() as session:
            user = session.get(User, user_id)
            if user is None:
                raise PermissionError("This token's account no longer exists.")
            return fn(session, user, *args, **kwargs)

    return await anyio.to_thread.run_sync(call)


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
async def search_library(query: str, limit: int = 8) -> dict:
    """Find saved items by words or topic. Matches titles, tags, summaries, notes and the
    full text, and returns each item with the passage that matched and a link to it."""
    return await _run(assistant.search, get_embedder(), query, limit)


@server.tool(annotations=READ_ONLY)
async def ask_library(
    question: str, item_ids: list[int] | None = None, tags: list[str] | None = None
) -> dict:
    """Answer a question from the library only, with numbered sources (passages, pages and
    links). Limit it to some items (ids from search_library) or tags when that helps. Says
    so when the library doesn't cover the question; it never guesses."""
    return await _run(assistant.ask, get_embedder(), get_llm(), question, item_ids, tags)


@server.tool(annotations=READ_ONLY)
async def get_item(item_id: int) -> dict:
    """One item: its summary, overview, key points, tags, the user's note, and the items
    most related to it."""
    return await _run(assistant.get_item, item_id)


@server.tool(annotations=READ_ONLY)
async def read_item(item_id: int, start: int = 0) -> dict:
    """An item's full text, about 12,000 characters at a time. For more, call again with
    the `next_start` it returns."""
    return await _run(assistant.read_item, item_id, start)


@server.tool(annotations=READ_ONLY)
async def list_items(tags: list[str] | None = None, limit: int = 20) -> dict:
    """Recently saved items, newest first; with `tags`, only items carrying all of them."""
    return await _run(assistant.list_items, tags, limit)


@server.tool(annotations=READ_ONLY)
async def list_tags() -> dict:
    """Every tag in the library and how many items carry it."""
    return await _run(assistant.list_tags)


@server.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def save_to_library(
    url: str | None = None, note: str | None = None, title: str | None = None
) -> dict:
    """Save a link (article, PDF or YouTube video) or a note to the library. Only when the
    user asks to save something. Recall reads it in the background and tags it."""
    return await _run(assistant.save, url, note, title)


def _allowed_hosts() -> list[str]:
    """Host headers accepted at /mcp (DNS-rebinding protection): the public API host, and
    any local port while developing. "testserver" is what the test client sends."""
    from urllib.parse import urlsplit

    return [urlsplit(api_url).netloc, "localhost:*", "127.0.0.1:*", "testserver"]


app = server.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=_allowed_hosts()),
)

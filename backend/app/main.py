import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import (
    ask,
    auth,
    cards,
    chats,
    chunks,
    connections,
    highlights,
    images,
    items,
    search,
    tags,
)
from app.config import get_settings
from app.db import engine
from app.mcp_server import app as mcp_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = None
    # Show Recall's own log lines (items read, questions answered) next to uvicorn's.
    recall_log = logging.getLogger("recall")
    if not recall_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        recall_log.addHandler(handler)
        recall_log.setLevel(logging.INFO)
    if get_settings().run_worker_in_api:
        from app.worker import start_in_background

        stop = start_in_background()
    # The MCP endpoint's sessions live as long as the API does.
    async with mcp_app.router.lifespan_context(mcp_app):
        yield
    if stop is not None:
        stop.set()


app = FastAPI(title="Recall API", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(items.router)
app.include_router(tags.router)
app.include_router(ask.router)
app.include_router(chunks.router)
app.include_router(chats.router)
app.include_router(highlights.router)
app.include_router(search.router)
app.include_router(cards.router)
app.include_router(connections.router)
app.include_router(images.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}


@app.get("/ping", tags=["meta"])
def ping() -> dict[str, str]:
    """Up, without touching the database: for the host's health checks and keep-awake pings,
    so a free database that sleeps when idle (Neon) isn't kept awake by them."""
    return {"status": "ok"}


# Last, so the API's own routes win: /mcp for AI assistants (app/mcp_server.py), and its
# OAuth protected-resource metadata under /.well-known.
app.mount("/", mcp_app)

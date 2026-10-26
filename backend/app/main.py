from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import ask, auth, cards, chats, chunks, highlights, items, search, tags
from app.config import get_settings
from app.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = None
    if get_settings().run_worker_in_api:
        from app.worker import start_in_background

        stop = start_in_background()
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


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import ask, auth, chats, chunks, items, tags
from app.config import get_settings
from app.db import engine

app = FastAPI(title="Recall API", version="0.3.0")

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


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}

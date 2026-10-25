"""FastAPI dependencies for the heavy services, so tests can swap in fakes."""

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.embeddings import Embedder, get_embedder
from app.services.llm import LLMClient, LLMError, get_llm

SessionDep = Annotated[Session, Depends(get_session)]


def embedder_dep() -> Embedder:
    return get_embedder()


def llm_dep() -> LLMClient:
    try:
        return get_llm()
    except LLMError as exc:
        raise HTTPException(503, str(exc)) from exc


EmbedderDep = Annotated[Embedder, Depends(embedder_dep)]
LLMDep = Annotated[LLMClient, Depends(llm_dep)]

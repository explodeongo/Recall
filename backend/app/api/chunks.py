from fastapi import APIRouter, HTTPException

from app.deps import SessionDep
from app.models import Chunk
from app.schemas import ChunkOut

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get("/{chunk_id}", response_model=ChunkOut)
def get_chunk(chunk_id: int, session: SessionDep) -> Chunk:
    """A cited passage, so the UI can show exactly where an answer came from (NFR-3)."""
    chunk = session.get(Chunk, chunk_id)
    if chunk is None:
        raise HTTPException(404, "Passage not found")
    return chunk

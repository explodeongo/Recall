from fastapi import APIRouter, HTTPException

from app.deps import CurrentUser, SessionDep
from app.models import Chunk, Item
from app.schemas import ChunkOut

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get("/{chunk_id}", response_model=ChunkOut)
def get_chunk(chunk_id: int, session: SessionDep, user: CurrentUser) -> Chunk:
    """A cited passage, so the UI can show exactly where an answer came from (NFR-3)."""
    chunk = session.get(Chunk, chunk_id)
    if chunk is None or session.get(Item, chunk.item_id).user_id != user.id:
        raise HTTPException(404, "Passage not found")
    return chunk

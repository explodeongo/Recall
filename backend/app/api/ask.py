from fastapi import APIRouter, HTTPException

from app.schemas import AskIn

router = APIRouter(tags=["ask"])


@router.post("/ask")
def ask(body: AskIn) -> None:
    """Answer a question from saved content with citations (FR-5). Lands in milestone 3."""
    raise HTTPException(501, "Question answering is not built yet")

from fastapi import APIRouter, Depends, Query
from typing import Optional
from uuid import UUID

from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    document_id: Optional[UUID] = None,
    folder_id: Optional[UUID] = None,
    tags: Optional[list[str]] = Query(None),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Hybrid search: dense (pgvector) + sparse (BM25) + question match, fused with RRF."""
    # TODO: implement 4-stage retrieval funnel
    pass

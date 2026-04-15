from fastapi import APIRouter, Depends, Query
from typing import Optional
from uuid import UUID

from app.auth import get_current_user
from app.database import get_db
from app.services.embedder import embed_query
from app.services.retriever import retrieve
from app.services.reranker import rerank
from app.services.user_reranker import apply_user_signals
from app.services.user_context import get_or_create_user
from sqlalchemy import text

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
    user_row = await get_or_create_user(db, user)

    scoped_doc_ids: list[UUID] | None = [document_id] if document_id else None
    if tags:
        tag_rows = (
            await db.execute(
                text(
                    """
                    SELECT d.id
                    FROM documents d
                    LEFT JOIN permissions p_doc
                        ON p_doc.document_id = d.id AND p_doc.grantee_id = :uid
                    LEFT JOIN permissions p_folder
                        ON p_folder.folder_id = d.folder_id AND p_folder.grantee_id = :uid
                    WHERE (d.user_id = :uid OR p_doc.grantee_id = :uid OR p_folder.grantee_id = :uid)
                      AND d.tags && :tags
                    """
                ),
                {"uid": user_row["id"], "tags": tags},
            )
        ).mappings().all()
        tag_doc_ids = [r["id"] for r in tag_rows]
        if scoped_doc_ids:
            scoped_doc_ids = [d for d in scoped_doc_ids if d in tag_doc_ids]
        else:
            scoped_doc_ids = tag_doc_ids

    query_embedding = await embed_query(q)
    candidates = await retrieve(
        user_id=user_row["id"],
        query_text=q,
        query_embedding=query_embedding,
        db=db,
        document_ids=scoped_doc_ids,
        folder_id=folder_id,
    )
    reranked = await rerank(q, candidates, top_n=max(limit * 2, limit), use_llm=False)
    personalized = await apply_user_signals(
        user_id=user_row["id"],
        query_embedding=query_embedding,
        chunks=reranked,
        db=db,
        top_n=limit,
    )
    return {"query": q, "count": len(personalized), "results": personalized[:limit]}

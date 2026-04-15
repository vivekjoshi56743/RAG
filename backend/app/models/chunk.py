import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.database import Base

# Vertex text-embedding-005 embeddings (768 dims).
# Migrated from Voyage voyage-3 (1024 dims) via
# infra/sql/002_vertex_vector_768_migration.sql — keep this constant in lock-step
# with the vector(N) column type in the database.
EMBEDDING_DIM = 768


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)

    # Structural metadata
    section: Mapped[str | None] = mapped_column(String)
    section_heading: Mapped[str | None] = mapped_column(String)
    part: Mapped[str | None] = mapped_column(String)
    parent_chunk_id: Mapped[str | None] = mapped_column(String)

    # Extraction provenance: "native" | "ocr" | "ocr_low_conf" | "hybrid"
    source_type: Mapped[str | None] = mapped_column(String)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    question_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    hypothetical_questions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

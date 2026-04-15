from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
import sys
import types

if "firebase_admin" not in sys.modules:
    firebase_admin_module = types.ModuleType("firebase_admin")
    firebase_admin_module.initialize_app = lambda *_args, **_kwargs: object()

    credentials_module = types.ModuleType("firebase_admin.credentials")
    credentials_module.ApplicationDefault = lambda: object()

    auth_module = types.ModuleType("firebase_admin.auth")
    auth_module.verify_id_token = lambda _token: {"uid": "mocked"}

    firebase_admin_module.credentials = credentials_module
    firebase_admin_module.auth = auth_module
    sys.modules["firebase_admin"] = firebase_admin_module
    sys.modules["firebase_admin.credentials"] = credentials_module
    sys.modules["firebase_admin.auth"] = auth_module

from app.auth import get_current_user
from app.database import get_db
from app.main import app
from app.routers import chat, documents, feedback, folders, permissions, search, sharing


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None, rowcount: int = 1):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def mappings(self) -> "FakeResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def scalar_one(self) -> Any:
        return self._scalar


@dataclass
class FakeState:
    user_id: str = field(default_factory=lambda: str(uuid4()))
    user_email: str = "owner@example.com"
    grantee_id: str = field(default_factory=lambda: str(uuid4()))
    document_id: str = field(default_factory=lambda: str(uuid4()))
    folder_id: str = field(default_factory=lambda: str(uuid4()))
    conversation_id: str = field(default_factory=lambda: str(uuid4()))
    permission_id: str = field(default_factory=lambda: str(uuid4()))
    share_token: str = "sharetoken1"
    now: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    documents: list[dict[str, Any]] = field(default_factory=list)
    folders: list[dict[str, Any]] = field(default_factory=list)
    permissions: list[dict[str, Any]] = field(default_factory=list)
    conversations: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    shared_threads: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.documents = [
            {
                "id": self.document_id,
                "user_id": self.user_id,
                "name": "semantic.md",
                "file_path": "gs://bucket/path/semantic.md",
                "file_size": 100,
                "mime_type": "text/markdown",
                "status": "indexed",
                "document_type": "markdown",
                "created_at": self.now,
                "updated_at": self.now,
            }
        ]
        self.folders = [
            {
                "id": self.folder_id,
                "user_id": self.user_id,
                "name": "Default",
                "color": "#D4A853",
                "icon": "folder",
                "sort_order": 0,
                "created_at": self.now,
                "doc_count": 1,
            }
        ]
        self.permissions = [
            {
                "id": self.permission_id,
                "document_id": self.document_id,
                "role": "viewer",
                "created_at": self.now,
                "user_id": self.grantee_id,
                "email": "teammate@example.com",
                "display_name": "Teammate",
            }
        ]
        self.conversations = [
            {
                "id": self.conversation_id,
                "user_id": self.user_id,
                "title": "New Chat",
                "created_at": self.now,
                "updated_at": self.now,
                "last_message": None,
                "last_message_at": None,
            }
        ]
        self.messages = [
            {
                "id": str(uuid4()),
                "conversation_id": self.conversation_id,
                "role": "assistant",
                "content": "Hello from assistant",
                "citations": [],
                "created_at": self.now,
            }
        ]
        self.shared_threads = [
            {
                "share_token": self.share_token,
                "owner_id": self.user_id,
                "title": "New Chat",
                "snapshot": {"messages": self.messages},
                "view_count": 0,
                "created_at": self.now,
                "is_active": True,
            }
        ]


class FakeDB:
    def __init__(self, state: FakeState):
        self.state = state

    async def execute(self, statement, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        params = params or {}

        if "INSERT INTO documents" in sql and "RETURNING" in sql:
            created = {
                "id": params["id"],
                "user_id": params["uid"],
                "name": params["name"],
                "file_path": params["file_path"],
                "file_size": params["file_size"],
                "mime_type": params["mime_type"],
                "status": "uploaded",
                "created_at": self.state.now,
            }
            self.state.documents.append(created)
            return FakeResult([created])
        if "SELECT DISTINCT" in sql and "FROM documents d" in sql:
            rows = [{**doc, "user_role": "owner"} for doc in self.state.documents]
            return FakeResult(rows)
        if "SELECT * FROM documents WHERE id = :id" in sql:
            row = next((d for d in self.state.documents if d["id"] == params["id"]), None)
            return FakeResult([row] if row else [])
        if "SELECT file_path FROM documents WHERE id = :id" in sql:
            row = next((d for d in self.state.documents if d["id"] == params["id"]), None)
            return FakeResult([{"file_path": row["file_path"]}] if row else [])
        if "DELETE FROM documents WHERE id = :id" in sql:
            before = len(self.state.documents)
            self.state.documents = [d for d in self.state.documents if d["id"] != params["id"]]
            return FakeResult(rowcount=1 if len(self.state.documents) != before else 0)
        if "UPDATE documents" in sql and "WHERE id = :doc_id" in sql:
            for doc in self.state.documents:
                if doc["id"] == params["doc_id"]:
                    doc["folder_id"] = params["folder_id"]
            return FakeResult()
        if "UPDATE documents" in sql and "WHERE id = ANY(:doc_ids)" in sql:
            for doc in self.state.documents:
                if doc["id"] in params["doc_ids"]:
                    doc["folder_id"] = params["folder_id"]
            return FakeResult()
        if "INSERT INTO folders" in sql:
            created = {
                "id": str(uuid4()),
                "user_id": params["uid"],
                "name": params["name"],
                "color": params["color"],
                "icon": params["icon"],
                "created_at": self.state.now,
            }
            self.state.folders.append(created)
            return FakeResult([created])
        if "SELECT f.*, COUNT(d.id) AS doc_count" in sql:
            return FakeResult(self.state.folders)
        if "UPDATE folders" in sql:
            return FakeResult()
        if "DELETE FROM folders WHERE id = :id" in sql:
            self.state.folders = [f for f in self.state.folders if f["id"] != params["id"]]
            return FakeResult()
        if "UPDATE documents SET folder_id = NULL" in sql:
            for doc in self.state.documents:
                if doc.get("folder_id") == params["folder_id"]:
                    doc["folder_id"] = None
            return FakeResult()
        if "SELECT id FROM users WHERE email = :email" in sql:
            return FakeResult([{"id": self.state.grantee_id}] if params["email"] else [])
        if "INSERT INTO permissions" in sql:
            return FakeResult()
        if "SELECT p.id, p.role, p.created_at, u.id AS user_id, u.email, u.display_name" in sql:
            return FakeResult(self.state.permissions)
        if "DELETE FROM permissions WHERE id = :perm_id AND document_id = :doc_id" in sql:
            return FakeResult()
        if "INSERT INTO conversations" in sql:
            created = {
                "id": str(uuid4()),
                "user_id": params["uid"],
                "title": "New Chat",
                "created_at": self.state.now,
                "updated_at": self.state.now,
            }
            self.state.conversations.insert(0, created)
            return FakeResult([created])
        if "FROM conversations c" in sql and "LEFT JOIN LATERAL" in sql:
            rows = []
            for conv in self.state.conversations:
                rows.append(
                    {
                        "id": conv["id"],
                        "title": conv["title"],
                        "created_at": conv["created_at"],
                        "updated_at": conv["updated_at"],
                        "last_message": conv.get("last_message"),
                        "last_message_at": conv.get("last_message_at"),
                    }
                )
            return FakeResult(rows)
        if "SELECT * FROM conversations WHERE id = :id AND user_id = :uid" in sql:
            row = next(
                (c for c in self.state.conversations if c["id"] == params["id"] and c["user_id"] == params["uid"]),
                None,
            )
            return FakeResult([row] if row else [])
        if "SELECT id, role, content, citations, created_at" in sql and "FROM messages" in sql:
            rows = [m for m in self.state.messages if m["conversation_id"] == params["id"]]
            return FakeResult(rows)
        if "INSERT INTO messages (conversation_id, role, content, citations)" in sql:
            created = {
                "id": str(uuid4()),
                "conversation_id": params["conv_id"],
                "role": "user",
                "content": params["content"],
                "citations": [],
                "created_at": self.state.now,
            }
            self.state.messages.append(created)
            return FakeResult()
        if "UPDATE conversations SET updated_at = now() WHERE id = :id" in sql:
            return FakeResult()
        if "SELECT role, content" in sql and "FROM messages" in sql:
            rows = [
                {"role": m["role"], "content": m["content"]}
                for m in self.state.messages
                if m["conversation_id"] == params["id"]
            ]
            return FakeResult(rows)
        if "DELETE FROM conversations WHERE id = :id AND user_id = :uid" in sql:
            self.state.conversations = [
                c for c in self.state.conversations if not (c["id"] == params["id"] and c["user_id"] == params["uid"])
            ]
            return FakeResult()
        if "SELECT id, title FROM conversations WHERE id = :id AND user_id = :uid" in sql:
            row = next(
                (c for c in self.state.conversations if c["id"] == params["id"] and c["user_id"] == params["uid"]),
                None,
            )
            if not row:
                return FakeResult([])
            return FakeResult([{"id": row["id"], "title": row["title"]}])
        if "SELECT role, content, citations, created_at" in sql and "FROM messages" in sql:
            rows = [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "citations": m.get("citations", []),
                    "created_at": m["created_at"],
                }
                for m in self.state.messages
                if m["conversation_id"] == params["id"]
            ]
            return FakeResult(rows)
        if "INSERT INTO shared_threads" in sql:
            self.state.shared_threads.append(
                {
                    "share_token": params["token"],
                    "owner_id": params["owner_id"],
                    "title": params["title"],
                    "snapshot": {"messages": []},
                    "view_count": 0,
                    "created_at": self.state.now,
                    "is_active": True,
                }
            )
            return FakeResult()
        if "UPDATE shared_threads" in sql and "SET view_count = view_count + 1" in sql:
            row = next(
                (
                    t
                    for t in self.state.shared_threads
                    if t["share_token"] == params["token"] and t["is_active"] is True
                ),
                None,
            )
            if row is None:
                return FakeResult([])
            row["view_count"] += 1
            return FakeResult(
                [
                    {
                        "title": row["title"],
                        "snapshot": row["snapshot"],
                        "view_count": row["view_count"],
                        "created_at": row["created_at"],
                    }
                ]
            )
        if "UPDATE shared_threads" in sql and "SET is_active = false" in sql:
            row = next(
                (
                    t
                    for t in self.state.shared_threads
                    if t["share_token"] == params["token"] and t["owner_id"] == params["owner_id"]
                ),
                None,
            )
            if row is None:
                return FakeResult(rowcount=0)
            row["is_active"] = False
            return FakeResult(rowcount=1)
        if "INSERT INTO user_feedback" in sql:
            return FakeResult()

        return FakeResult([])

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.fixture
def client_and_state(monkeypatch):
    state = FakeState()
    fake_db = FakeDB(state)

    async def fake_user():
        return {"uid": state.user_id, "email": state.user_email}

    async def fake_get_db():
        yield fake_db

    async def fake_get_or_create_user(_db, _user):
        return {"id": state.user_id, "email": state.user_email}

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_get_db

    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(folders, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(permissions, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(chat, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(search, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(feedback, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(sharing, "get_or_create_user", fake_get_or_create_user)

    async def always_allowed(*_args, **_kwargs):
        return True

    monkeypatch.setattr(documents, "user_has_document_access", always_allowed)
    monkeypatch.setattr(documents, "user_has_folder_access", always_allowed)
    monkeypatch.setattr(folders, "user_has_folder_access", always_allowed)
    monkeypatch.setattr(permissions, "user_has_document_access", always_allowed)

    monkeypatch.setattr(documents, "upload_file", lambda **_kwargs: "https://storage.googleapis.com/mock/uploaded.pdf")
    monkeypatch.setattr(documents, "delete_file", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(documents, "_run_pipeline", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(documents.asyncio, "create_task", lambda *_args, **_kwargs: None)

    async def fake_embed_query(_query: str):
        return [0.1, 0.2, 0.3]

    async def fake_retrieve(**_kwargs):
        return [
            {
                "id": str(uuid4()),
                "document_id": state.document_id,
                "doc_name": "semantic.md",
                "content": "BM25 and vector scoring",
                "page_number": 1,
                "mime_type": "text/markdown",
                "document_type": "markdown",
                "file_path": "https://storage.googleapis.com/mock/semantic.md",
                "rrf_score": 0.0123,
            }
        ]

    async def fake_rerank(_query: str, chunks: list[dict[str, Any]], **_kwargs):
        return [{**chunks[0], "rerank_score": 0.77}]

    async def fake_apply_user_signals(**kwargs):
        chunks = kwargs["chunks"]
        return [{**chunks[0], "final_score": 0.89}]

    monkeypatch.setattr(search, "embed_query", fake_embed_query)
    monkeypatch.setattr(search, "retrieve", fake_retrieve)
    monkeypatch.setattr(search, "rerank", fake_rerank)
    monkeypatch.setattr(search, "apply_user_signals", fake_apply_user_signals)

    async def fake_run_rag_pipeline(**_kwargs):
        return (
            [
                {
                    "id": str(uuid4()),
                    "document_id": state.document_id,
                    "doc_name": "semantic.md",
                    "page_number": 2,
                    "content": "Chunk used in answer",
                }
            ],
            [{"role": "user", "content": "hello"}],
        )

    async def fake_stream_response(_messages):
        yield "Test token response."

    async def fake_persist(*_args, **_kwargs):
        return None

    monkeypatch.setattr(chat, "run_rag_pipeline", fake_run_rag_pipeline)
    monkeypatch.setattr(chat, "stream_response", fake_stream_response)
    monkeypatch.setattr(chat, "_persist_assistant_message", fake_persist)

    monkeypatch.setattr(feedback, "embed_query", fake_embed_query)

    with TestClient(app) as client:
        yield client, state

    app.dependency_overrides.clear()

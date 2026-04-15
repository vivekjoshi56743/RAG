from __future__ import annotations

from uuid import uuid4


def test_documents_api_contracts(client_and_state):
    client, state = client_and_state

    upload = client.post(
        "/api/documents/upload",
        files={"file": ("contract.md", b"# semantic search", "text/markdown")},
    )
    assert upload.status_code == 200
    upload_data = upload.json()
    assert {"id", "name", "file_path", "status"} <= set(upload_data.keys())

    listed = client.get("/api/documents")
    assert listed.status_code == 200
    listed_data = listed.json()
    assert isinstance(listed_data, list)
    assert listed_data and {"id", "name", "file_path", "status"} <= set(listed_data[0].keys())

    fetched = client.get(f"/api/documents/{state.document_id}")
    assert fetched.status_code == 200
    assert {"id", "name", "file_path", "status"} <= set(fetched.json().keys())

    moved = client.put(f"/api/documents/{state.document_id}/move", json={"folder_id": state.folder_id})
    assert moved.status_code == 200
    assert moved.json()["moved"] is True

    bulk_moved = client.put("/api/documents/bulk-move", json={"document_ids": [state.document_id], "folder_id": state.folder_id})
    assert bulk_moved.status_code == 200
    assert bulk_moved.json()["moved"] == 1

    deleted = client.delete(f"/api/documents/{state.document_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    invalid_upload = client.post(
        "/api/documents/upload",
        files={"file": ("contract.exe", b"MZ", "application/octet-stream")},
    )
    assert invalid_upload.status_code == 400


def test_permissions_and_folders_contracts(client_and_state):
    client, state = client_and_state

    share_doc = client.post(
        f"/api/documents/{state.document_id}/share",
        json={"email": "teammate@example.com", "role": "viewer"},
    )
    assert share_doc.status_code == 200
    assert share_doc.json()["shared"] is True

    perms = client.get(f"/api/documents/{state.document_id}/permissions")
    assert perms.status_code == 200
    perms_data = perms.json()
    assert isinstance(perms_data, list)
    assert perms_data and {"id", "role", "user_id", "email"} <= set(perms_data[0].keys())

    revoked = client.delete(f"/api/documents/{state.document_id}/permissions/{state.permission_id}")
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True

    folders_list = client.get("/api/folders")
    assert folders_list.status_code == 200
    folders_data = folders_list.json()
    assert isinstance(folders_data, list)
    assert folders_data and {"id", "name", "color", "icon"} <= set(folders_data[0].keys())

    created_folder = client.post("/api/folders", json={"name": "New Folder", "color": "#123456", "icon": "folder"})
    assert created_folder.status_code == 200
    assert {"id", "name", "color", "icon"} <= set(created_folder.json().keys())

    updated_folder = client.put(f"/api/folders/{state.folder_id}", json={"name": "Renamed", "color": "#fff111", "icon": "folder"})
    assert updated_folder.status_code == 200
    assert updated_folder.json()["updated"] is True

    shared_folder = client.post(
        f"/api/folders/{state.folder_id}/share",
        json={"email": "teammate@example.com", "role": "viewer"},
    )
    assert shared_folder.status_code == 200
    assert shared_folder.json()["shared"] is True

    deleted_folder = client.delete(f"/api/folders/{state.folder_id}")
    assert deleted_folder.status_code == 200
    assert deleted_folder.json()["deleted"] is True

    invalid_role = client.post(
        f"/api/folders/{state.folder_id}/share",
        json={"email": "teammate@example.com", "role": "super-admin"},
    )
    assert invalid_role.status_code == 400


def test_search_chat_shared_and_feedback_contracts(client_and_state):
    client, state = client_and_state

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    search_response = client.get("/api/search", params={"q": "semantic ranking", "limit": 5})
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert {"query", "count", "results"} <= set(search_data.keys())
    assert search_data["results"] and {"content", "doc_name", "final_score", "rerank_score", "file_path"} <= set(
        search_data["results"][0].keys()
    )

    invalid_search = client.get("/api/search", params={"q": "", "limit": 0})
    assert invalid_search.status_code == 422

    created = client.post("/api/conversations")
    assert created.status_code == 200
    assert {"id", "title"} <= set(created.json().keys())

    listed = client.get("/api/conversations")
    assert listed.status_code == 200
    listed_data = listed.json()
    assert isinstance(listed_data, list)
    assert listed_data and {"id", "title", "created_at", "updated_at"} <= set(listed_data[0].keys())

    fetched = client.get(f"/api/conversations/{state.conversation_id}")
    assert fetched.status_code == 200
    fetched_data = fetched.json()
    assert {"id", "title", "messages"} <= set(fetched_data.keys())
    assert isinstance(fetched_data["messages"], list)

    streamed = client.post(
        f"/api/conversations/{state.conversation_id}/messages",
        json={"content": "what is semantic ranking?"},
    )
    assert streamed.status_code == 200
    assert "text/event-stream" in streamed.headers.get("content-type", "")
    assert '"type": "token"' in streamed.text
    assert '"type": "done"' in streamed.text

    invalid_message = client.post(f"/api/conversations/{state.conversation_id}/messages", json={"content": "   "})
    assert invalid_message.status_code == 400

    shared = client.post(f"/api/conversations/{state.conversation_id}/share")
    assert shared.status_code == 200
    share_token = shared.json()["share_token"]
    assert isinstance(share_token, str) and len(share_token) > 0

    shared_get = client.get(f"/api/shared/{state.share_token}")
    assert shared_get.status_code == 200
    shared_data = shared_get.json()
    assert {"title", "messages", "view_count", "shared_at"} <= set(shared_data.keys())

    shared_delete = client.delete(f"/api/shared/{state.share_token}")
    assert shared_delete.status_code == 200
    assert shared_delete.json()["revoked"] is True

    missing_shared = client.get(f"/api/shared/{uuid4()}")
    assert missing_shared.status_code == 404

    feedback_response = client.post(
        "/api/feedback",
        json={
            "query_text": "semantic ranking",
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "signal_type": "thumbs_up",
            "metadata": {"source": "test"},
        },
    )
    assert feedback_response.status_code == 200
    assert feedback_response.json()["stored"] is True

    unsupported_feedback = client.post(
        "/api/feedback",
        json={
            "query_text": "semantic ranking",
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "signal_type": "not-supported",
            "metadata": {},
        },
    )
    assert unsupported_feedback.status_code == 200
    assert unsupported_feedback.json()["stored"] is False

    deleted = client.delete(f"/api/conversations/{state.conversation_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

import type {
  ChatStreamEvent,
  Conversation,
  ConversationDetail,
  Document,
  Folder,
  PermissionEntry,
  SearchResponse,
  SharedThreadResponse,
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface RequestOptions extends Omit<RequestInit, "body"> {
  token?: string;
  body?: BodyInit | object;
}

function buildHeaders(token?: string, hasJsonBody = false, extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {};
  if (hasJsonBody) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return { ...headers, ...(extra ?? {}) };
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { token, body, headers, ...init } = options;
  const isJsonBody = Boolean(body) && !(body instanceof FormData);
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: buildHeaders(token, isJsonBody, headers),
    body: isJsonBody ? JSON.stringify(body) : (body as BodyInit | undefined),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}

// Documents
export async function uploadDocument(file: File, token: string): Promise<Document> {
  const form = new FormData();
  form.append("file", file);
  return request<Document>("/api/documents/upload", { method: "POST", token, body: form });
}

export const listDocuments = (token: string) => request<Document[]>("/api/documents", { token });
export const getDocument = (id: string, token: string) => request<Document>(`/api/documents/${id}`, { token });
export const deleteDocument = (id: string, token: string) =>
  request<{ deleted: boolean }>(`/api/documents/${id}`, { method: "DELETE", token });
export const moveDocument = (id: string, folder_id: string | null, token: string) =>
  request<{ moved: boolean }>(`/api/documents/${id}/move`, { method: "PUT", token, body: { folder_id } });
export const bulkMoveDocuments = (document_ids: string[], folder_id: string | null, token: string) =>
  request<{ moved: number }>("/api/documents/bulk-move", { method: "PUT", token, body: { document_ids, folder_id } });

// Permissions
export const shareDocument = (docId: string, email: string, role: "viewer" | "editor" | "admin", token: string) =>
  request<{ shared: boolean }>(`/api/documents/${docId}/share`, { method: "POST", token, body: { email, role } });
export const listDocumentPermissions = (docId: string, token: string) =>
  request<PermissionEntry[]>(`/api/documents/${docId}/permissions`, { token });
export const revokeDocumentPermission = (docId: string, permissionId: string, token: string) =>
  request<{ revoked: boolean }>(`/api/documents/${docId}/permissions/${permissionId}`, {
    method: "DELETE",
    token,
  });

// Folders
export const listFolders = (token: string) => request<Folder[]>("/api/folders", { token });
export const createFolder = (body: { name: string; color?: string; icon?: string }, token: string) =>
  request<Folder>("/api/folders", { method: "POST", token, body });
export const updateFolder = (id: string, body: { name: string; color?: string; icon?: string }, token: string) =>
  request<{ updated: boolean }>(`/api/folders/${id}`, { method: "PUT", token, body });
export const deleteFolder = (id: string, token: string) =>
  request<{ deleted: boolean }>(`/api/folders/${id}`, { method: "DELETE", token });
export const shareFolder = (id: string, email: string, role: "viewer" | "editor" | "admin", token: string) =>
  request<{ shared: boolean }>(`/api/folders/${id}/share`, { method: "POST", token, body: { email, role } });

// Search
export async function search(
  token: string,
  params: {
    q: string;
    limit?: number;
    document_id?: string;
    folder_id?: string;
    tags?: string[];
  },
) {
  const query = new URLSearchParams();
  query.set("q", params.q);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.document_id) query.set("document_id", params.document_id);
  if (params.folder_id) query.set("folder_id", params.folder_id);
  (params.tags ?? []).forEach((tag) => query.append("tags", tag));
  return request<SearchResponse>(`/api/search?${query.toString()}`, { token });
}

// Chat
export const createConversation = (token: string) =>
  request<Conversation>("/api/conversations", { method: "POST", token });
export const listConversations = (token: string, q?: string) => {
  const url = q ? `/api/conversations?q=${encodeURIComponent(q)}` : "/api/conversations";
  return request<Conversation[]>(url, { token });
};
export const getConversation = (id: string, token: string) =>
  request<ConversationDetail>(`/api/conversations/${id}`, { token });
export const renameConversation = (id: string, title: string, token: string) =>
  request<Conversation>(`/api/conversations/${id}`, { method: "PATCH", token, body: { title } });
export const deleteConversation = (id: string, token: string) =>
  request<{ deleted: boolean }>(`/api/conversations/${id}`, { method: "DELETE", token });
export const shareConversation = (id: string, token: string) =>
  request<{ share_token: string }>(`/api/conversations/${id}/share`, { method: "POST", token });

export async function* streamConversationMessage(
  convId: string,
  payload: { content: string; document_ids?: string[]; folder_id?: string | null },
  token: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(`${API_BASE}/api/conversations/${convId}/messages`, {
    method: "POST",
    headers: buildHeaders(token, true),
    body: JSON.stringify(payload),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error((await res.text()) || "Streaming request failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const raw of events) {
      const line = raw
        .split("\n")
        .find((entry) => entry.startsWith("data:"))
        ?.slice(5)
        .trim();
      if (!line) continue;
      try {
        yield JSON.parse(line) as ChatStreamEvent;
      } catch {
        // Ignore malformed SSE payload chunks.
      }
    }
  }
}

// Shared thread
export const getSharedThread = (token: string) =>
  request<SharedThreadResponse>(`/api/shared/${token}`, { cache: "no-store" });
export const revokeSharedThread = (token: string, authToken: string) =>
  request<{ revoked: boolean }>(`/api/shared/${token}`, { method: "DELETE", token: authToken });

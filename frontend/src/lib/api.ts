const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, ...init } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res.json();
}

// ─── Documents ──────────────────────────────────────────────────────────────

export async function uploadDocument(file: File, token: string) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/documents/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const listDocuments = (token: string) =>
  request("/api/documents", { token });

export const getDocument = (id: string, token: string) =>
  request(`/api/documents/${id}`, { token });

export const deleteDocument = (id: string, token: string) =>
  request(`/api/documents/${id}`, { method: "DELETE", token });

// ─── Search ─────────────────────────────────────────────────────────────────

export const search = (q: string, token: string, params?: Record<string, string>) => {
  const qs = new URLSearchParams({ q, ...params }).toString();
  return request(`/api/search?${qs}`, { token });
};

// ─── Chat ────────────────────────────────────────────────────────────────────

export const listConversations = (token: string) =>
  request("/api/conversations", { token });

export const createConversation = (token: string) =>
  request("/api/conversations", { method: "POST", token });

export const deleteConversation = (id: string, token: string) =>
  request(`/api/conversations/${id}`, { method: "DELETE", token });

export function streamMessage(convId: string, content: string, token: string): EventSource {
  // Use SSE for streaming responses
  const url = `${API_BASE}/api/conversations/${convId}/messages?token=${token}`;
  // POST via fetch for streaming; EventSource doesn't support POST.
  // Actual streaming is handled via fetch + ReadableStream in the component.
  throw new Error("Use fetchStream() for streaming responses.");
}

export async function* fetchStream(convId: string, content: string, token: string) {
  const res = await fetch(`${API_BASE}/api/conversations/${convId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ content }),
  });
  if (!res.ok || !res.body) throw new Error(await res.text());
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    yield decoder.decode(value, { stream: true });
  }
}

// ─── Folders ─────────────────────────────────────────────────────────────────

export const listFolders = (token: string) =>
  request("/api/folders", { token });

export const createFolder = (body: { name: string; color?: string; icon?: string }, token: string) =>
  request("/api/folders", { method: "POST", body: JSON.stringify(body), token });

export const deleteFolder = (id: string, token: string) =>
  request(`/api/folders/${id}`, { method: "DELETE", token });

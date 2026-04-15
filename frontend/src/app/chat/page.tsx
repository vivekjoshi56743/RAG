"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ChatMessage } from "@/components/ChatMessage";
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  listFolders,
  shareConversation,
  streamConversationMessage,
} from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { Citation, Conversation, Folder, Message } from "@/lib/types";

function normalizeCitations(value: unknown): Citation[] {
  if (Array.isArray(value)) return value as Citation[];
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? (parsed as Citation[]) : [];
    } catch {
      return [];
    }
  }
  return [];
}

export default function ChatPage() {
  const { user, loading, getIdToken } = useRequireAuth();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFolderId, setSelectedFolderId] = useState("");
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const activeConversation = useMemo(
    () => conversations.find((conv) => conv.id === activeConversationId) ?? null,
    [conversations, activeConversationId],
  );

  const loadConversations = async () => {
    const token = await getIdToken();
    if (!token) return;
    const [rows, folderRows] = await Promise.all([listConversations(token), listFolders(token)]);
    setConversations(rows);
    setFolders(folderRows);
    if (!rows.length) {
      const created = await createConversation(token);
      setConversations([created]);
      setActiveConversationId(created.id);
      return;
    }
    setActiveConversationId((current) => current || rows[0].id);
  };

  const loadMessages = async (conversationId: string) => {
    const token = await getIdToken();
    if (!token) return;
    const detail = await getConversation(conversationId, token);
    setMessages(
      (detail.messages ?? []).map((msg) => ({
        ...msg,
        citations: normalizeCitations(msg.citations),
      })),
    );
  };

  useEffect(() => {
    if (!loading && user) {
      void loadConversations();
    }
  }, [loading, user]);

  useEffect(() => {
    if (activeConversationId) {
      void loadMessages(activeConversationId);
    }
  }, [activeConversationId]);

  const onCreateConversation = async () => {
    setError(null);
    try {
      const token = await getIdToken();
      if (!token) return;
      const created = await createConversation(token);
      setConversations((prev) => [created, ...prev]);
      setActiveConversationId(created.id);
      setMessages([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed creating conversation");
    }
  };

  const onDeleteConversation = async (conversationId: string) => {
    if (!window.confirm("Delete this conversation?")) return;
    setError(null);
    try {
      const token = await getIdToken();
      if (!token) return;
      await deleteConversation(conversationId, token);
      const remaining = conversations.filter((conv) => conv.id !== conversationId);
      setConversations(remaining);
      if (!remaining.length) {
        const created = await createConversation(token);
        setConversations([created]);
        setActiveConversationId(created.id);
        setMessages([]);
      } else if (activeConversationId === conversationId) {
        setActiveConversationId(remaining[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed deleting conversation");
    }
  };

  const onSend = async () => {
    if (!input.trim() || !activeConversationId || sending) return;
    const content = input.trim();
    setInput("");
    setSending(true);
    setError(null);
    setShareUrl(null);

    const userMessage: Message = {
      id: `local-user-${Date.now()}`,
      role: "user",
      content,
      citations: [],
    };
    const assistantMessageId = `local-assistant-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantMessageId, role: "assistant", content: "", citations: [] },
    ]);

    abortRef.current?.abort();
    const aborter = new AbortController();
    abortRef.current = aborter;

    try {
      const token = await getIdToken();
      if (!token) return;

      for await (const event of streamConversationMessage(
        activeConversationId,
        { content, folder_id: selectedFolderId || undefined },
        token,
        aborter.signal,
      )) {
        if (event.type === "token") {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId ? { ...msg, content: msg.content + event.text } : msg,
            ),
          );
        } else if (event.type === "done") {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId ? { ...msg, citations: event.citations ?? [] } : msg,
            ),
          );
        } else if (event.type === "error") {
          setError(event.message || "Assistant stream failed");
        }
      }

      await Promise.all([loadMessages(activeConversationId), loadConversations()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? { ...msg, content: "Sorry, I ran into an error while generating the response." }
            : msg,
        ),
      );
    } finally {
      setSending(false);
    }
  };

  const onShareConversation = async () => {
    if (!activeConversationId) return;
    try {
      const token = await getIdToken();
      if (!token) return;
      const response = await shareConversation(activeConversationId, token);
      const base = window.location.origin;
      setShareUrl(`${base}/shared/${response.share_token}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed sharing conversation");
    }
  };

  if (loading || (!user && !loading)) {
    return <div className="p-6">Loading...</div>;
  }

  return (
    <AppShell
      title="Chat"
      folders={folders}
      activeFolderId={selectedFolderId || null}
      onFolderClick={(folderId) => setSelectedFolderId(folderId ?? "")}
      actions={
        <div className="flex gap-2">
          <button onClick={() => void onCreateConversation()} className="rounded bg-blue-600 text-white px-3 py-2 text-sm">
            New Chat
          </button>
          <button
            onClick={() => void onShareConversation()}
            disabled={!activeConversation}
            className="rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100 disabled:opacity-50"
          >
            Share
          </button>
        </div>
      }
    >
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 h-[calc(100vh-140px)]">
        <aside className="rounded-xl border bg-white p-3 overflow-auto">
          <h2 className="text-sm font-semibold mb-2">Conversations</h2>
          <div className="space-y-2">
            {conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => setActiveConversationId(conv.id)}
                className={`w-full rounded border px-3 py-2 text-left text-sm ${
                  conv.id === activeConversationId ? "bg-blue-50 border-blue-200" : "hover:bg-slate-50"
                }`}
              >
                <div className="font-medium truncate">{conv.title || "Untitled"}</div>
                <div className="text-xs text-slate-500 truncate">{conv.last_message ?? "No messages yet"}</div>
                <div className="mt-1 flex justify-end">
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      void onDeleteConversation(conv.id);
                    }}
                    className="text-red-600 text-xs"
                  >
                    Delete
                  </span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="rounded-xl border bg-white flex flex-col overflow-hidden">
          <div className="flex-1 overflow-auto p-4 space-y-3 bg-slate-50">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
          </div>
          <div className="border-t p-3 space-y-2">
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            {shareUrl ? (
              <div className="rounded border bg-slate-50 p-2 text-sm">
                Shared URL: <span className="break-all">{shareUrl}</span>
              </div>
            ) : null}
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question across your documents..."
                rows={3}
                className="flex-1 rounded border px-3 py-2 text-sm"
              />
              <button
                onClick={() => void onSend()}
                disabled={sending || !input.trim()}
                className="rounded bg-slate-900 text-white px-4 py-2 text-sm disabled:opacity-50 self-end"
              >
                {sending ? "Streaming..." : "Send"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

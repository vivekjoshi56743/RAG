"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { ChevronLeft, ChevronRight, Copy, Plus, Share2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { ChatMessage } from "@/components/ChatMessage";
import { ConfirmModal } from "@/components/ConfirmModal";
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  listFolders,
  renameConversation,
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
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFolderId, setSelectedFolderId] = useState("");
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [renamingConversationId, setRenamingConversationId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [chatSearchQuery, setChatSearchQuery] = useState("");
  const [convToDelete, setConvToDelete] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const debouncedSearchQuery = useDebounce(chatSearchQuery, 300);

  const activeConversation = useMemo(
    () => conversations.find((conv) => conv.id === activeConversationId) ?? null,
    [conversations, activeConversationId],
  );

  const loadConversations = async (query?: string) => {
    const token = await getIdToken();
    if (!token) return;
    const [rows, folderRows] = await Promise.all([listConversations(token, query), listFolders(token)]);
    setConversations(rows);
    setFolders(folderRows);
    if (!rows.length && !query) {
      const created = await createConversation(token);
      setConversations([created]);
      setActiveConversationId(created.id);
      return;
    }
    if (!query && rows.length && !activeConversationId) {
        setActiveConversationId(rows[0].id);
    }
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
      void loadConversations(debouncedSearchQuery);
    }
  }, [loading, user, debouncedSearchQuery]);

  useEffect(() => {
    if (activeConversationId) {
      void loadMessages(activeConversationId);
    }
  }, [activeConversationId]);

  const onCreateConversation = async () => {
    try {
      const token = await getIdToken();
      if (!token) return;
      const created = await createConversation(token);
      setConversations((prev) => [created, ...prev]);
      setActiveConversationId(created.id);
      setMessages([]);
      toast.success("New chat started");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed creating conversation");
    }
  };

  const performDeleteConversation = async () => {
    if (!convToDelete) return;
    try {
      const token = await getIdToken();
      if (!token) return;
      await deleteConversation(convToDelete, token);
      const remaining = conversations.filter((conv) => conv.id !== convToDelete);
      setConversations(remaining);
      if (!remaining.length) {
        const created = await createConversation(token);
        setConversations([created]);
        setActiveConversationId(created.id);
        setMessages([]);
      } else if (activeConversationId === convToDelete) {
        setActiveConversationId(remaining[0].id);
      }
      toast.success("Conversation deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed deleting conversation");
    } finally {
      setConvToDelete(null);
    }
  };

  const startRenameConversation = (conversation: Conversation) => {
    setRenamingConversationId(conversation.id);
    setRenameValue(conversation.title || "");
    setError(null);
  };

  const cancelRenameConversation = () => {
    setRenamingConversationId(null);
    setRenameValue("");
    setRenaming(false);
  };

  const submitRenameConversation = async (conversationId: string) => {
    const title = renameValue.trim();
    if (!title) {
      toast.error("Conversation title cannot be empty");
      return;
    }

    try {
      setRenaming(true);
      const token = await getIdToken();
      if (!token) return;
      const updated = await renameConversation(conversationId, title, token);
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === conversationId
            ? {
                ...conv,
                title: updated.title,
                updated_at: updated.updated_at ?? conv.updated_at,
                last_message: updated.last_message ?? conv.last_message,
                last_message_at: updated.last_message_at ?? conv.last_message_at,
              }
            : conv,
        ),
      );
      cancelRenameConversation();
      toast.success("Renamed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed renaming conversation");
    } finally {
      setRenaming(false);
    }
  };

  const onSend = async () => {
    if (!input.trim() || !activeConversationId || sending) return;
    const content = input.trim();
    const priorUserCount = messages.filter((m) => m.role === "user").length;
    const priorAssistantCount = messages.filter((m) => m.role === "assistant").length;
    const shouldAttemptFallbackTitle =
      (activeConversation?.title || "").trim() === "New Chat" &&
      priorUserCount === 0 &&
      priorAssistantCount === 0;

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
          if (event.title?.trim()) {
            const sseTitle = event.title.trim();
            setConversations((prev) =>
              prev.map((conv) => (conv.id === activeConversationId ? { ...conv, title: sseTitle } : conv)),
            );
          } else if (shouldAttemptFallbackTitle) {
            // Fallback: persist a deterministic title when auto-title payload is missing.
            // This avoids chats getting stuck as "New Chat" in degraded model/API scenarios.
            const token = await getIdToken();
            if (token) {
              const fallbackTitle = deriveTitleFromPrompt(content);
              const updated = await renameConversation(activeConversationId, fallbackTitle, token);
              setConversations((prev) =>
                prev.map((conv) =>
                  conv.id === activeConversationId
                    ? {
                        ...conv,
                        title: updated.title,
                        updated_at: updated.updated_at ?? conv.updated_at,
                      }
                    : conv,
                ),
              );
            }
          }
        } else if (event.type === "error") {
          toast.error(event.message || "Assistant stream failed");
        }
      }

      await Promise.all([loadMessages(activeConversationId), loadConversations(debouncedSearchQuery)]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to send message");
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
      toast.success("Share link generated");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed sharing conversation");
    }
  };

  if (loading || (!user && !loading)) {
    return <div className="p-6">Loading...</div>;
  }

  return (
    <AppShell
      title="Chat"
      folders={folders}
      actions={
        <div className="flex gap-2">
          <button onClick={() => void onCreateConversation()} className="btn-primary flex items-center gap-1.5" type="button">
            <Plus className="h-4 w-4" />
            New Chat
          </button>
          <button
            onClick={() => void onShareConversation()}
            disabled={!activeConversation}
            className="btn-secondary flex items-center gap-1.5"
            type="button"
          >
            <Share2 className="h-4 w-4" />
            Share
          </button>
        </div>
      }
    >
      <div className={`grid h-full gap-4 transition-all duration-300 ${sidebarOpen ? "lg:grid-cols-[300px_1fr]" : "lg:grid-cols-[0px_1fr]"}`}>
        <aside className={`surface-card flex h-full flex-col overflow-hidden p-0 transition-all duration-300 ${sidebarOpen ? "w-[300px] opacity-100" : "w-0 opacity-0 pointer-events-none"}`}>
          <div className="flex h-full flex-col overflow-y-auto p-3">
          <div className="mb-3 space-y-2">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Conversations</h2>
            <input
              type="text"
              value={chatSearchQuery}
              onChange={(e) => setChatSearchQuery(e.target.value)}
              placeholder="Search chats..."
              className="input-base w-full text-sm"
            />
          </div>
          <div className="space-y-2">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                className={`rounded-xl border p-2 transition ${
                  conv.id === activeConversationId
                    ? "border-brand-300 bg-brand-50 shadow-sm dark:border-brand-500/40 dark:bg-brand-500/10"
                    : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50 dark:hover:border-slate-600 dark:hover:bg-slate-800"
                }`}
              >
                <button
                  onClick={() => setActiveConversationId(conv.id)}
                  className="w-full rounded-lg px-1 pb-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                  type="button"
                >
                  <div className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{conv.title || "Untitled"}</div>
                  <div className="truncate pt-1 text-xs text-slate-500 dark:text-slate-400">{conv.last_message ?? "No messages yet"}</div>
                </button>
                {renamingConversationId === conv.id ? (
                  <div className="mt-2 space-y-2">
                    <input
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          void submitRenameConversation(conv.id);
                        } else if (event.key === "Escape") {
                          cancelRenameConversation();
                        }
                      }}
                      className="input-base w-full"
                      placeholder="Conversation title"
                      maxLength={120}
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={cancelRenameConversation}
                        className="btn-ghost"
                        disabled={renaming}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => void submitRenameConversation(conv.id)}
                        className="btn-secondary"
                        disabled={renaming || !renameValue.trim()}
                      >
                        {renaming ? "Saving..." : "Save"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-2 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => startRenameConversation(conv)}
                      className="btn-ghost text-xs"
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      onClick={() => setConvToDelete(conv.id)}
                      className="btn-danger text-xs"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            ))}
            {conversations.length === 0 && (
              <div className="p-2 text-center text-xs text-slate-500">
                No conversations found.
              </div>
            )}
          </div>
          </div>
        </aside>

        <section className="surface-card relative flex h-full flex-col overflow-hidden p-0">
          <button
            type="button"
            onClick={() => setSidebarOpen((o) => !o)}
            className="absolute left-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700 transition-colors"
            title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            {sidebarOpen ? <ChevronLeft className="h-4 w-4 text-slate-500" /> : <ChevronRight className="h-4 w-4 text-slate-500" />}
          </button>
          <div className="flex-1 overflow-auto bg-slate-50 dark:bg-slate-900/50 p-4">
            <div className="space-y-3 mx-auto max-w-4xl">
              {messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  onCitationClick={(citation) => setActiveCitation(citation)}
                />
              ))}
            </div>
          </div>
          <div className="border-t border-slate-200 dark:border-slate-800 p-4">
            <div className="space-y-3 max-w-4xl mx-auto">
              {shareUrl ? (
                <div className="flex items-center justify-between gap-3 rounded-xl border border-brand-200 bg-brand-50 p-3 text-sm text-slate-700 dark:bg-brand-500/10 dark:border-brand-500/20 dark:text-brand-200">
                  <span className="break-all font-medium truncate">{shareUrl}</span>
                  <button
                    onClick={() => {
                      void navigator.clipboard.writeText(shareUrl);
                      toast.success("URL copied");
                    }}
                    className="btn-primary !px-3 !py-1 flex items-center gap-1.5 shrink-0"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    Copy
                  </button>
                </div>
              ) : null}
              {activeCitation ? (
                <div className="rounded-xl border border-brand-200 bg-brand-50 p-3 text-sm text-slate-700">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-slate-900">
                        Source: {activeCitation.doc_name}
                        {activeCitation.page != null ? ` · p.${activeCitation.page}` : ""}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-700">
                        {activeCitation.snippet || "No snippet available for this citation."}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setActiveCitation(null)}
                      className="btn-ghost !px-2 !py-1 !text-xs"
                    >
                      Close
                    </button>
                  </div>
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      className="btn-secondary !px-2 !py-1 !text-xs"
                      onClick={() => {
                        if (!activeCitation.snippet) return;
                        setInput((prev) =>
                          prev.trim()
                            ? `${prev.trim()}\n\nUse this source context:\n${activeCitation.snippet}`
                            : `Use this source context:\n${activeCitation.snippet}`,
                        );
                      }}
                    >
                      Use In Prompt
                    </button>
                    <button
                      type="button"
                      className="btn-secondary !px-2 !py-1 !text-xs"
                      onClick={() => {
                        if (!activeCitation.snippet) return;
                        void navigator.clipboard.writeText(activeCitation.snippet);
                      }}
                    >
                      Copy Snippet
                    </button>
                  </div>
                </div>
              ) : null}
              {folders.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="shrink-0 text-xs font-medium text-slate-500 dark:text-slate-400">Search in:</span>
                  <select
                    value={selectedFolderId}
                    onChange={(e) => setSelectedFolderId(e.target.value)}
                    className="select-base !py-1.5 !text-xs"
                  >
                    <option value="">All folders</option>
                    {folders.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.icon} {f.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div className="flex gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask a question across your documents..."
                  rows={3}
                  className="input-base min-h-[96px] flex-1 resize-y"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      void onSend();
                    }
                  }}
                />
                <button
                  onClick={() => void onSend()}
                  disabled={sending || !input.trim()}
                  className="btn-primary self-end"
                  type="button"
                >
                  {sending ? "Streaming..." : "Send"}
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
      <ConfirmModal
        isOpen={Boolean(convToDelete)}
        title="Delete Conversation"
        message="Are you sure you want to delete this conversation? This will permanently remove all messages."
        onConfirm={performDeleteConversation}
        onCancel={() => setConvToDelete(null)}
      />
    </AppShell>
  );
}

function deriveTitleFromPrompt(prompt: string): string {
  const cleaned = prompt
    .replace(/[^\w\s-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "New Chat";
  const words = cleaned.split(" ").slice(0, 6);
  const titled = words
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
  return titled.slice(0, 120);
}

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

"use client";
import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { AppShell } from "@/components/AppShell";
import { MarkdownViewer } from "@/components/MarkdownViewer";
import { SearchResultItem } from "@/components/SearchResult";
import { listDocuments, listFolders, search } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { Document, Folder, SearchResult } from "@/lib/types";

function pickRelevanceScore(result: SearchResult): number {
  const candidates = [result.final_score, result.rerank_score, result.rrf_score, result.signal_score, result.score];
  for (const candidate of candidates) {
    if (typeof candidate === "number" && Number.isFinite(candidate)) {
      return candidate;
    }
  }
  return 0;
}



export default function SearchPage() {
  const { user, loading, getIdToken } = useRequireAuth();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedFolderId, setSelectedFolderId] = useState("");
  const [tags, setTags] = useState("");
  const [limit, setLimit] = useState(5);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [viewerText, setViewerText] = useState("");
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQuery(query.trim()), 350);
    return () => clearTimeout(id);
  }, [query]);

  useEffect(() => {
    if (!user) return;
    void (async () => {
      const token = await getIdToken();
      if (!token) return;
      const [folderRows, docRows] = await Promise.all([listFolders(token), listDocuments(token)]);
      setFolders(folderRows);
      setDocuments(docRows);
    })();
  }, [user, getIdToken]);

  useEffect(() => {
    if (!debouncedQuery || !user) {
      setResults([]);
      return;
    }
    void (async () => {
      setSearching(true);
      try {
        const token = await getIdToken();
        if (!token) return;
        const response = await search(token, {
          q: debouncedQuery,
          limit,
          document_id: selectedDocumentId || undefined,
          folder_id: selectedFolderId || undefined,
          tags: tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        });
        const normalized = response.results.map((result) => {
          const snippet = result.snippet ?? result.content ?? "";
          return {
            ...result,
            snippet,
            score: pickRelevanceScore(result),
          };
        });
        setResults(normalized);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Search failed");
      } finally {
        setSearching(false);
      }
    })();
  }, [debouncedQuery, user, limit, selectedDocumentId, selectedFolderId, tags, getIdToken]);

  const resultCountLabel = useMemo(
    () => (searching ? "Searching..." : `${results.length} result${results.length === 1 ? "" : "s"}`),
    [searching, results.length],
  );

  const onSelectResult = (result: SearchResult) => {
    setSelectedResult(result);
    setViewerText(result.content ?? result.snippet ?? "");
  };

  if (loading || (!user && !loading)) {
    return <div className="p-6">Loading...</div>;
  }

  return (
    <AppShell title="Semantic Search" folders={folders}>
      <div className="grid h-full grid-cols-1 gap-4 xl:grid-cols-[1.25fr_1fr]">
        <section className="surface-card flex h-full flex-col overflow-y-auto p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask naturally, e.g. what are the payment terms?"
              className="input-base md:col-span-2"
            />
            <select
              value={selectedDocumentId}
              onChange={(e) => setSelectedDocumentId(e.target.value)}
              className="select-base"
            >
              <option value="">All documents</option>
              {documents.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.name}
                </option>
              ))}
            </select>
            <select
              value={selectedFolderId}
              onChange={(e) => setSelectedFolderId(e.target.value)}
              className="select-base"
            >
              <option value="">All folders</option>
              {folders.map((folder) => (
                <option key={folder.id} value={folder.id}>
                  {folder.name}
                </option>
              ))}
            </select>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="Tags (comma separated)"
              className="input-base"
            />
            <input
              type="number"
              min={1}
              max={20}
              value={limit}
              onChange={(e) => setLimit(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
              className="input-base"
            />
          </div>
          <div className="mt-3 flex items-center justify-between text-sm text-slate-600 dark:text-slate-400">
            <span>{resultCountLabel}</span>
          </div>

          <div className="mt-3 space-y-3">
            {results.map((result, idx) => (
              <SearchResultItem key={`${result.chunk_id ?? result.id ?? idx}-${idx}`} result={result} onClick={() => void onSelectResult(result)} />
            ))}
          </div>
        </section>

        <section className="surface-card flex h-full flex-col overflow-y-auto p-5">
          {selectedResult ? (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-brand-700 dark:text-brand-400">
                  {selectedResult.doc_name}
                </span>
                {(selectedResult.page ?? selectedResult.page_number) ? (
                  <span className="text-xs text-slate-500">
                    p.{selectedResult.page ?? selectedResult.page_number}
                  </span>
                ) : null}
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 font-sans text-sm dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-100">
                <MarkdownViewer content={viewerText || "No text content available for this chunk."} />
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">
              Select a result to view its text content.
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

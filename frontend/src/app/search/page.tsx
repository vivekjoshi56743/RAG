"use client";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PDFViewer, type ViewerKind } from "@/components/PDFViewer";
import { SearchResultItem } from "@/components/SearchResult";
import { getDocument, listDocuments, listFolders, search } from "@/lib/api";
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

function inferViewerKind(result: SearchResult, filePath?: string, mimeType?: string | null, documentType?: string | null): ViewerKind {
  const source = `${mimeType ?? ""} ${documentType ?? ""} ${result.doc_name ?? ""} ${filePath ?? ""}`.toLowerCase();
  if (source.includes("pdf") || source.endsWith(".pdf")) return "pdf";
  if (source.includes("markdown") || source.includes("text") || source.endsWith(".md") || source.endsWith(".txt") || source.endsWith(".docx")) {
    return "text";
  }
  return "unknown";
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
  const [limit, setLimit] = useState(20);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [viewerDocPath, setViewerDocPath] = useState("");
  const [viewerKind, setViewerKind] = useState<ViewerKind>("unknown");
  const [viewerText, setViewerText] = useState("");
  const [error, setError] = useState<string | null>(null);
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
      setError(null);
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
        setError(err instanceof Error ? err.message : "Search failed");
      } finally {
        setSearching(false);
      }
    })();
  }, [debouncedQuery, user, limit, selectedDocumentId, selectedFolderId, tags, getIdToken]);

  const resultCountLabel = useMemo(
    () => (searching ? "Searching..." : `${results.length} result${results.length === 1 ? "" : "s"}`),
    [searching, results.length],
  );

  const onSelectResult = async (result: SearchResult) => {
    setSelectedResult(result);
    setViewerText(result.content ?? result.snippet ?? "");
    const initialFilePath = result.file_path ?? "";
    setViewerDocPath(initialFilePath);
    setViewerKind(inferViewerKind(result, initialFilePath, result.mime_type, result.document_type));
    const docId = result.document_id ?? result.doc_id;
    if (!docId) return;
    const token = await getIdToken();
    if (!token) return;
    try {
      const doc = await getDocument(docId, token);
      setViewerDocPath(doc.file_path ?? "");
      setViewerKind(inferViewerKind(result, doc.file_path ?? "", doc.mime_type, doc.document_type));
    } catch {
      if (!initialFilePath) {
        setViewerDocPath("");
        setViewerKind("unknown");
      }
    }
  };

  if (loading || (!user && !loading)) {
    return <div className="p-6">Loading...</div>;
  }

  return (
    <AppShell title="Semantic Search" folders={folders}>
      <div className="grid grid-cols-1 xl:grid-cols-[1.25fr_1fr] gap-4 h-[calc(100vh-140px)]">
        <section className="rounded-xl border bg-white p-4 overflow-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask naturally, e.g. what are the payment terms?"
              className="md:col-span-2 rounded border px-3 py-2 text-sm"
            />
            <select
              value={selectedDocumentId}
              onChange={(e) => setSelectedDocumentId(e.target.value)}
              className="rounded border px-3 py-2 text-sm"
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
              className="rounded border px-3 py-2 text-sm"
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
              className="rounded border px-3 py-2 text-sm"
            />
            <input
              type="number"
              min={1}
              max={100}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 20)}
              className="rounded border px-3 py-2 text-sm"
            />
          </div>
          <div className="mt-3 flex items-center justify-between text-sm text-slate-600">
            <span>{resultCountLabel}</span>
          </div>
          {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}

          <div className="mt-3 space-y-3">
            {results.map((result, idx) => (
              <SearchResultItem key={`${result.chunk_id ?? result.id ?? idx}-${idx}`} result={result} onClick={() => void onSelectResult(result)} />
            ))}
          </div>
        </section>

        <section className="rounded-xl border bg-white overflow-hidden">
          {selectedResult ? (
            <PDFViewer
              url={viewerDocPath}
              initialPage={selectedResult.page ?? selectedResult.page_number ?? 1}
              highlightText={selectedResult.snippet}
              viewerKind={viewerKind}
              textPreview={viewerText}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-sm text-slate-500">
              Select a result to view source context.
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

import type { Document } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  uploaded: "bg-slate-100 text-slate-700",
  processing: "bg-yellow-100 text-yellow-700",
  indexed: "bg-green-100 text-green-700",
  error: "bg-red-100 text-red-700",
};

interface Props {
  document: Document;
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
  onOpenPermissions?: () => void;
  onMove?: (folderId: string | null) => void;
  onDelete?: () => void;
  folderOptions?: Array<{ id: string; name: string }>;
}

export function DocumentCard({
  document,
  selected,
  onSelect,
  onOpenPermissions,
  onMove,
  onDelete,
  folderOptions = [],
}: Props) {
  const summary = normalizeDocumentSummary(document.summary);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-brand-200 hover:shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          {onSelect ? (
            <input
              type="checkbox"
              checked={Boolean(selected)}
              onChange={(e) => onSelect(e.target.checked)}
              className="mt-1 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
          ) : null}
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-slate-900">{document.name}</h3>
            <p className="text-xs text-slate-500">
              {document.user_role ?? "owner"} · {document.num_pages ?? 0} pages · {document.num_chunks ?? 0} chunks
            </p>
          </div>
        </div>
        <span className={`ml-2 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[document.status] ?? ""}`}>
          {document.status}
        </span>
      </div>
      {summary ? <p className="mt-2 line-clamp-2 text-sm text-slate-600">{summary}</p> : null}
      <div className="mt-2 flex flex-wrap gap-1">
        {document.key_topics?.map((t) => (
          <span key={t} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            {t}
          </span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {onOpenPermissions ? (
          <button
            onClick={onOpenPermissions}
            className="btn-secondary !px-2 !py-1 !text-xs"
            type="button"
          >
            Permissions
          </button>
        ) : null}
        {onMove ? (
          <select
            value={document.folder_id ?? ""}
            onChange={(e) => onMove(e.target.value || null)}
            className="select-base !rounded-lg !px-2 !py-1 !text-xs"
          >
            <option value="">Unfiled</option>
            {folderOptions.map((folder) => (
              <option key={folder.id} value={folder.id}>
                {folder.name}
              </option>
            ))}
          </select>
        ) : null}
        {onDelete ? (
          <button
            onClick={onDelete}
            className="btn-danger !rounded-lg !px-2 !py-1 !text-xs"
            type="button"
          >
            Delete
          </button>
        ) : null}
      </div>
    </div>
  );
}

function normalizeDocumentSummary(raw?: string | null): string {
  if (!raw) return "";
  const trimmed = raw.trim();
  const unfenced = stripJsonFence(trimmed);

  try {
    const parsed = JSON.parse(unfenced);
    if (parsed && typeof parsed === "object" && typeof parsed.summary === "string") {
      return parsed.summary.trim();
    }
  } catch {
    // Not JSON; continue with plain-text cleanup.
  }

  const summaryMatch = unfenced.match(/"summary"\s*:\s*"([^"]+)/i);
  if (summaryMatch?.[1]) {
    return summaryMatch[1].trim();
  }

  return unfenced;
}

function stripJsonFence(text: string): string {
  let value = text.trim();
  if (value.startsWith("```")) {
    value = value.replace(/^```[a-zA-Z]*\s*/i, "");
    if (value.endsWith("```")) {
      value = value.slice(0, -3).trim();
    }
  }
  return value;
}

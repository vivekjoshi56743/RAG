import type { Document } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  uploaded: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400",
  processing: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  indexed: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  error: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400",
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
    <div className="surface-card p-5 group animate-in-fade">
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
            <h3 className="truncate text-base font-bold text-slate-900 dark:text-slate-100 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">{document.name}</h3>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-500 mt-0.5">
              {document.user_role ?? "owner"} · {document.num_pages ?? 0} pages · {document.num_chunks ?? 0} chunks
            </p>
          </div>
        </div>
        <span className={`ml-2 shrink-0 rounded-lg px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${STATUS_COLORS[document.status] ?? ""}`}>
          {document.status}
        </span>
      </div>
      {summary ? <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{summary}</p> : null}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {document.key_topics?.slice(0, 5).map((t) => (
          <span key={t} className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:text-slate-400 border dark:border-slate-700/50">
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

  // Match the summary value, allowing escaped quotes (\\" inside the string).
  const summaryMatch = unfenced.match(/"summary"\s*:\s*"((?:[^\\"]|\\.)*)/);
  if (summaryMatch?.[1]) {
    // Unescape any escaped quotes in the extracted value.
    return summaryMatch[1].replace(/\\"/g, '"').trim();
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

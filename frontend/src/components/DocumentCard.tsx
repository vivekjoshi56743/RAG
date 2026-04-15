import type { Document } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  uploaded: "bg-gray-100 text-gray-600",
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
  return (
    <div className="rounded-lg border bg-white p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          {onSelect ? (
            <input
              type="checkbox"
              checked={Boolean(selected)}
              onChange={(e) => onSelect(e.target.checked)}
              className="mt-1"
            />
          ) : null}
          <div className="min-w-0">
            <h3 className="font-medium truncate">{document.name}</h3>
            <p className="text-xs text-gray-500">
              {document.user_role ?? "owner"} · {document.num_pages ?? 0} pages · {document.num_chunks ?? 0} chunks
            </p>
          </div>
        </div>
        <span className={`text-xs rounded-full px-2 py-0.5 ml-2 shrink-0 ${STATUS_COLORS[document.status] ?? ""}`}>
          {document.status}
        </span>
      </div>
      {document.summary && <p className="mt-1 text-sm text-gray-500 line-clamp-2">{document.summary}</p>}
      <div className="mt-2 flex gap-1 flex-wrap">
        {document.key_topics?.map((t) => (
          <span key={t} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{t}</span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {onOpenPermissions ? (
          <button
            onClick={onOpenPermissions}
            className="rounded border px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
          >
            Permissions
          </button>
        ) : null}
        {onMove ? (
          <select
            value={document.folder_id ?? ""}
            onChange={(e) => onMove(e.target.value || null)}
            className="rounded border px-2 py-1 text-xs"
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
            className="rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
          >
            Delete
          </button>
        ) : null}
      </div>
    </div>
  );
}

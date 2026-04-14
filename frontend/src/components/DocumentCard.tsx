import type { Document } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  uploaded: "bg-gray-100 text-gray-600",
  processing: "bg-yellow-100 text-yellow-700",
  indexed: "bg-green-100 text-green-700",
  error: "bg-red-100 text-red-700",
};

interface Props {
  document: Document;
  onDelete?: () => void;
}

export function DocumentCard({ document, onDelete }: Props) {
  return (
    <div className="rounded-lg border p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <h3 className="font-medium truncate">{document.name}</h3>
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
    </div>
  );
}

import { CitationBadge } from "./CitationBadge";
import type { Message } from "@/lib/types";

interface Props {
  message: Message;
  onCitationClick?: (citation: Message["citations"][number]) => void;
}

export function ChatMessage({ message, onCitationClick }: Props) {
  return (
    <div className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl rounded-xl p-4 ${
          message.role === "user" ? "bg-blue-600 text-white" : "bg-white border text-slate-900"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.citations?.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.citations.map((c, i) => (
              <CitationBadge key={`${c.chunk_id}-${i}`} citation={c} onClick={() => onCitationClick?.(c)} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

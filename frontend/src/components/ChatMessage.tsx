import { CitationBadge } from "./CitationBadge";
import type { Message } from "@/lib/types";
import { MarkdownViewer } from "./MarkdownViewer";

interface Props {
  message: Message;
  onCitationClick?: (citation: Message["citations"][number]) => void;
}

export function ChatMessage({ message, onCitationClick }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl rounded-2xl p-4 shadow-sm ${
          isUser
            ? "bg-brand-600 text-white"
            : "border border-slate-200 bg-white text-slate-900"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        ) : (
          <MarkdownViewer content={message.content} />
        )}
        {message.citations?.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.citations.map((c, i) => (
              <CitationBadge
                key={`${c.chunk_id}-${i}`}
                citation={c}
                onClick={onCitationClick ? () => onCitationClick(c) : undefined}
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

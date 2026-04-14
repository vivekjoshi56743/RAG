import { CitationBadge } from "./CitationBadge";
import type { Message } from "@/lib/types";

interface Props {
  message: Message;
  onCitationClick?: (citation: Message["citations"][number]) => void;
}

export function ChatMessage({ message, onCitationClick }: Props) {
  // TODO: render user/assistant bubbles with inline [Source N] citation links
  return (
    <div className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      <div className="max-w-2xl rounded-lg p-4">
        <p>{message.content}</p>
        {message.citations?.map((c, i) => (
          <CitationBadge key={i} citation={c} onClick={() => onCitationClick?.(c)} />
        ))}
      </div>
    </div>
  );
}

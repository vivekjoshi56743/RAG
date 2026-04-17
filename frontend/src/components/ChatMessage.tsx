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
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"} animate-in-fade`}>
      <div
        className={`max-w-[85%] sm:max-w-2xl lg:max-w-3xl rounded-2xl p-4 shadow-sm transition-all duration-300 ${
          isUser
            ? "bg-gradient-to-br from-brand-600 to-indigo-600 text-white shadow-brand-500/20"
            : "border border-slate-200 bg-white/70 backdrop-blur-sm text-slate-900 dark:bg-slate-900/40 dark:border-slate-800 dark:text-slate-100 dark:shadow-none"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        ) : message.content === "" ? (
          <span className="flex items-center gap-1 py-1">
            <span className="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce [animation-delay:-0.3s]" />
            <span className="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce [animation-delay:-0.15s]" />
            <span className="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce" />
          </span>
        ) : (
          <MarkdownViewer
            content={message.content}
            citations={message.citations}
            onCitationClick={onCitationClick}
          />
        )}
        {(() => {
          const inlineSources = new Set(Array.from(message.content.matchAll(/\[Source\s+(\d+)\]/gi)).map(m => parseInt(m[1], 10)));
          const unreferencedCitations = message.citations?.filter(c => !inlineSources.has(c.source)) || [];

          if (unreferencedCitations.length === 0) return null;

          return (
            <div className="mt-4 flex flex-wrap gap-2 pt-3 border-t border-slate-100 dark:border-slate-800/50">
              {unreferencedCitations.map((c, i) => (
                <CitationBadge
                  key={`${c.chunk_id}-${i}`}
                  citation={c}
                  onClick={onCitationClick ? () => onCitationClick(c) : undefined}
                />
              ))}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

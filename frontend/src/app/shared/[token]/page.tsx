import type { SharedThreadResponse } from "@/lib/types";
import { ChatMessage } from "@/components/ChatMessage";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchSharedThread(token: string): Promise<SharedThreadResponse | null> {
  const res = await fetch(`${API_BASE}/api/shared/${token}`, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

function getCitations(value: unknown) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

export default async function SharedThreadPage({ params }: { params: { token: string } }) {
  const data = await fetchSharedThread(params.token);

  if (!data) {
    return (
      <main className="min-h-screen bg-slate-100 p-6">
        <section className="surface-card mx-auto max-w-3xl p-6">
          <h1 className="text-xl font-semibold">Shared thread unavailable</h1>
          <p className="mt-2 text-sm text-slate-600">This link may be revoked or expired.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-100 p-6">
      <section className="surface-card mx-auto max-w-4xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{data.title}</h1>
        <p className="mt-1 text-xs text-slate-500">Views: {data.view_count}</p>
        <div className="mt-4 space-y-3">
          {data.messages.map((message, idx) => (
            <ChatMessage
              key={`${message.id ?? idx}-${idx}`}
              message={{ ...message, citations: getCitations(message.citations) }}
            />
          ))}
        </div>
      </section>
    </main>
  );
}

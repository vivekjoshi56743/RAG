import type { SharedThreadResponse } from "@/lib/types";

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
      <main className="min-h-screen p-6 bg-slate-50">
        <section className="mx-auto max-w-3xl rounded-xl border bg-white p-6">
          <h1 className="text-xl font-semibold">Shared thread unavailable</h1>
          <p className="mt-2 text-sm text-slate-600">This link may be revoked or expired.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-6 bg-slate-50">
      <section className="mx-auto max-w-4xl rounded-xl border bg-white p-6">
        <h1 className="text-xl font-semibold">{data.title}</h1>
        <p className="text-xs text-slate-500 mt-1">Views: {data.view_count}</p>
        <div className="mt-4 space-y-3">
          {data.messages.map((message, idx) => (
            <div
              key={`${message.id ?? idx}-${idx}`}
              className={`rounded-lg p-3 ${
                message.role === "user" ? "bg-blue-600 text-white ml-8" : "bg-slate-100 text-slate-900 mr-8"
              }`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>
              {getCitations(message.citations).length ? (
                <div className="mt-2 text-xs">
                  {getCitations(message.citations).map((citation, citationIdx) => (
                    <span key={`${citation.chunk_id}-${citationIdx}`} className="mr-2">
                      {citation.doc_name} p.{citation.page ?? "-"}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

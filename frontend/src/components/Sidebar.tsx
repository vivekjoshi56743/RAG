"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Folder } from "@/lib/types";

interface Props {
  folders: Folder[];
  activeFolderId?: string;
  onFolderClick?: (id: string | null) => void;
}

const NAV_ITEMS = [
  { href: "/documents", label: "Documents", icon: "📚" },
  { href: "/search", label: "Search", icon: "🔍" },
  { href: "/chat", label: "Chat", icon: "💬" },
];

export function Sidebar({ folders, activeFolderId, onFolderClick }: Props) {
  const pathname = usePathname();

  return (
    <nav className="flex h-screen w-64 shrink-0 flex-col border-r border-slate-200 bg-white/90 backdrop-blur">
      <div className="border-b border-slate-200 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">Workspace</p>
        <p className="mt-1 text-lg font-semibold text-slate-900">RAG Engine</p>
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto p-3">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition
              ${
                pathname.startsWith(item.href)
                  ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
          >
            <span>{item.icon}</span>
            {item.label}
          </Link>
        ))}

        <div className="mt-5 px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Folders</div>
        <button
          onClick={() => onFolderClick?.(null)}
          className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          type="button"
        >
          📚 All Documents
        </button>
        {folders.map((f) => (
          <button
            key={f.id}
            onClick={() => onFolderClick?.(f.id)}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm transition
              ${
                activeFolderId === f.id
                  ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            type="button"
          >
            <span>{f.icon}</span>
            {f.name}
          </button>
        ))}
      </div>
    </nav>
  );
}

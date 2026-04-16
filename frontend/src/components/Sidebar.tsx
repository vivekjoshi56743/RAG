"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import type { Folder } from "@/lib/types";

interface Props {
  folders: Folder[];
}

const NAV_ITEMS = [
  { href: "/documents", label: "Documents", icon: "📚" },
  { href: "/search", label: "Search", icon: "🔍" },
  { href: "/chat", label: "Chat", icon: "💬" },
];

export function Sidebar({ folders }: Props) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeFolderId = searchParams.get("folderId");

  return (
    <nav className="flex h-screen w-64 shrink-0 flex-col border-r border-slate-200 bg-white/80 backdrop-blur-xl dark:border-slate-800 dark:bg-[#0b0e14]/80">
      <div className="border-b border-slate-200 p-6 dark:border-slate-800">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-brand-600 dark:text-brand-400">Workspace</p>
        <p className="mt-1 text-xl font-black tracking-tight text-slate-900 dark:text-slate-100">RAG Engine</p>
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto p-4 custom-scrollbar">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all duration-200
              ${
                pathname.startsWith(item.href)
                  ? "bg-brand-600 text-white shadow-md shadow-brand-500/20"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              }`}
          >
            <span className="text-lg">{item.icon}</span>
            {item.label}
          </Link>
        ))}

        <div className="mt-8 px-4 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400 dark:text-slate-600">Folders</div>
        <div className="mt-2 space-y-1">
          {folders.map((f) => (
            <Link
              key={f.id}
              href={`/documents?folderId=${f.id}`}
              className={`flex w-full items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200
                ${
                  activeFolderId === f.id
                    ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200 dark:bg-brand-500/10 dark:text-brand-300 dark:ring-brand-500/20"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                }`}
            >
              <span className="text-lg">{f.icon}</span>
              <span className="truncate">{f.name}</span>
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}

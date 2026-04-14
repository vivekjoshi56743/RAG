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
    <nav className="w-56 shrink-0 border-r bg-white flex flex-col h-full">
      <div className="p-4 border-b font-semibold text-lg">RAG Engine</div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors
              ${pathname.startsWith(item.href) ? "bg-blue-50 text-blue-700" : "text-gray-700 hover:bg-gray-100"}`}
          >
            <span>{item.icon}</span>
            {item.label}
          </Link>
        ))}

        <div className="mt-4 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Folders</div>
        <button
          onClick={() => onFolderClick?.(null)}
          className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
        >
          📚 All Documents
        </button>
        {folders.map((f) => (
          <button
            key={f.id}
            onClick={() => onFolderClick?.(f.id)}
            className={`w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors
              ${activeFolderId === f.id ? "bg-blue-50 text-blue-700" : "text-gray-700 hover:bg-gray-100"}`}
          >
            <span>{f.icon}</span>
            {f.name}
          </button>
        ))}
      </div>
    </nav>
  );
}

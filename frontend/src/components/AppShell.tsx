"use client";

import { type ReactNode } from "react";
import { Sidebar } from "@/components/Sidebar";
import type { Folder } from "@/lib/types";
import { useAuth } from "@/lib/auth";

interface Props {
  title: string;
  folders: Folder[];
  activeFolderId?: string | null;
  onFolderClick?: (folderId: string | null) => void;
  actions?: ReactNode;
  children: ReactNode;
}

export function AppShell({ title, folders, activeFolderId, onFolderClick, actions, children }: Props) {
  const { user, signOut } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50 flex">
      <Sidebar
        folders={folders}
        activeFolderId={activeFolderId ?? undefined}
        onFolderClick={onFolderClick}
      />
      <main className="flex-1 p-6">
        <header className="mb-4 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
            <p className="text-sm text-slate-600">{user?.email}</p>
          </div>
          <div className="flex items-center gap-2">
            {actions}
            <button
              onClick={() => void signOut()}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100"
            >
              Sign out
            </button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}

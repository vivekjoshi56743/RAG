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
    <div className="flex h-screen overflow-hidden bg-slate-100">
      <Sidebar
        folders={folders}
        activeFolderId={activeFolderId ?? undefined}
        onFolderClick={onFolderClick}
      />
      <main className="flex h-full flex-1 flex-col p-5 lg:p-6 overflow-hidden">
        <header className="mb-5 shrink-0 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
            <p className="mt-1 text-sm text-slate-600">{user?.email}</p>
          </div>
          <div className="flex items-center gap-2">
            {actions}
            <button
              onClick={() => void signOut()}
              className="btn-secondary"
            >
              Sign out
            </button>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      </main>
    </div>
  );
}

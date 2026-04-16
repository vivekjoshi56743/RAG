"use client";

import { type ReactNode } from "react";
import { Sidebar } from "@/components/Sidebar";
import type { Folder } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";

interface Props {
  title: string;
  folders: Folder[];
  actions?: ReactNode;
  children: ReactNode;
}

export function AppShell({ title, folders, actions, children }: Props) {
  const { user, signOut } = useAuth();
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100 dark:bg-slate-950 transition-colors duration-300">
      <Sidebar folders={folders} />
      <main className="flex h-full flex-1 flex-col p-5 lg:p-6 overflow-hidden">
        <header className="mb-5 shrink-0 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">{title}</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{user?.email}</p>
          </div>
          <div className="flex items-center gap-3">
            {actions}
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="rounded-full p-2 text-slate-500 hover:bg-slate-200 focus:outline-none dark:text-slate-400 dark:hover:bg-slate-800 transition"
              aria-label="Toggle Dark Mode"
            >
              {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
            </button>
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

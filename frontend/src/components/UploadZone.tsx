"use client";
import { useRef, useState } from "react";

interface Props {
  onUpload: (file: File) => Promise<void>;
}

export function UploadZone({ onUpload }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    Array.from(files).forEach((f) => onUpload(f));
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-300 animate-in-fade
        ${dragging 
          ? "border-brand-500 bg-brand-50/50 scale-[1.01] dark:bg-brand-500/10" 
          : "border-slate-300 bg-white/50 hover:border-brand-400 hover:bg-white dark:border-slate-800 dark:bg-slate-900/40 dark:hover:bg-slate-900/60"}`}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <div className="flex flex-col items-center gap-2">
        <div className="rounded-full bg-brand-100 p-3 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400">
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Drop files here or <span className="text-brand-600 dark:text-brand-400 underline underline-offset-4 pointer-events-none">browse</span>
          </p>
          <p className="mt-1 text-xs font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wider">PDF, DOCX, TXT, Markdown</p>
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md"
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </div>
  );
}

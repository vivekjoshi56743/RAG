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
      className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition
        ${dragging ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-white hover:border-brand-300 hover:bg-slate-50"}`}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <p className="text-sm text-slate-600">
        Drop files here or <span className="font-medium text-brand-600 underline">browse</span>
      </p>
      <p className="mt-1 text-xs text-slate-400">PDF, DOCX, TXT, Markdown</p>
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

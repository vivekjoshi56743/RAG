"use client";
// TODO: react-pdf (PDF.js wrapper) with page navigation and citation highlight
import { useState } from "react";

interface Props {
  url: string;
  initialPage?: number;
  highlightText?: string;
}

export function PDFViewer({ url, initialPage = 1, highlightText }: Props) {
  const [page, setPage] = useState(initialPage);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 border-b p-2 text-sm">
        <button onClick={() => setPage((p) => Math.max(1, p - 1))}>←</button>
        <span>Page {page}</span>
        <button onClick={() => setPage((p) => p + 1)}>→</button>
      </div>
      <div className="flex-1 overflow-auto bg-gray-100 flex items-center justify-center">
        {/* react-pdf Document + Page will go here */}
        <p className="text-gray-400 text-sm">PDF Viewer — {url}</p>
      </div>
    </div>
  );
}

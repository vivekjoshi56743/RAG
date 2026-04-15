"use client";
import { useEffect, useMemo, useState } from "react";

export type ViewerKind = "pdf" | "text" | "unknown";

interface Props {
  url: string;
  initialPage?: number;
  highlightText?: string;
  textPreview?: string;
  viewerKind?: ViewerKind;
}

export function PDFViewer({ url, initialPage = 1, highlightText, textPreview, viewerKind = "unknown" }: Props) {
  const [page, setPage] = useState(initialPage);

  useEffect(() => {
    setPage(initialPage);
  }, [initialPage]);

  const isHttpUrl = useMemo(() => /^https?:\/\//i.test(url), [url]);
  const canRenderPdf = viewerKind === "pdf" && isHttpUrl;
  const showTextPreview = viewerKind === "text";
  const previewText = textPreview || highlightText || "No preview text available for this document.";
  const pdfUrlWithPage = canRenderPdf ? `${url}${url.includes("#") ? "&" : "#"}page=${page}` : "";

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 border-b p-2 text-sm">
        <button onClick={() => setPage((p) => Math.max(1, p - 1))}>←</button>
        <span>Page {page}</span>
        <button onClick={() => setPage((p) => p + 1)}>→</button>
      </div>
      <div className="flex-1 overflow-auto bg-gray-100 flex items-center justify-center">
        {canRenderPdf ? (
          <iframe
            title="Document preview"
            src={pdfUrlWithPage}
            className="w-full h-full border-0"
          />
        ) : (
          <div className="max-w-2xl p-4 text-sm text-slate-700">
            <p className="font-medium mb-2">Viewer source</p>
            <p className="break-all text-xs text-slate-500">{url || "No file URL available"}</p>
            {viewerKind === "pdf" && !isHttpUrl ? (
              <p className="mt-2 text-xs text-amber-700">
                PDF preview needs an HTTP(S) URL. This source currently points to a storage path.
              </p>
            ) : null}
            {showTextPreview ? (
              <>
                <p className="font-medium mt-4 mb-1">Text preview</p>
                <pre className="rounded border bg-white p-3 whitespace-pre-wrap break-words">{previewText}</pre>
              </>
            ) : highlightText ? (
              <>
                <p className="font-medium mt-4 mb-1">Highlighted context</p>
                <p className="rounded border bg-white p-3">{highlightText}</p>
              </>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

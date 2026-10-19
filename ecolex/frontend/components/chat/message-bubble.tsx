"use client";

import { useState } from "react";
import { openDocumentFile } from "@/lib/documents";
import { getErrorMessage } from "@/lib/errors";
import type { MessageItem } from "@/lib/types";
import { ErrorBanner } from "@/components/ui/error-banner";

export function MessageBubble({ message }: { message: MessageItem }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [viewError, setViewError] = useState<string | null>(null);
  const isUser = message.role === "user";

  async function handleViewSource(source: NonNullable<MessageItem["source_chunks"]>[number]) {
    setViewError(null);
    try {
      await openDocumentFile(source.document_id, source.pagina_origen);
    } catch (err) {
      setViewError(getErrorMessage(err, "No se pudo abrir el documento original."));
    }
  }

  if (isUser) {
    return (
      <div className="flex flex-col items-end gap-1 max-w-2xl self-end">
        <div className="p-space-md bg-secondary text-on-secondary rounded-2xl rounded-tr-none shadow-md font-body-md text-body-md leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  const sources = message.source_chunks ?? [];

  return (
    <div className="flex items-start gap-space-sm max-w-3xl self-start">
      <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center shadow-md flex-shrink-0">
        <span className="material-symbols-outlined text-[18px] text-secondary-fixed">neurology</span>
      </div>
      <div className="flex flex-col gap-space-xs flex-1">
        <div className="p-space-md bg-surface-container-lowest rounded-2xl rounded-tl-none shadow-md flex flex-col gap-space-sm">
          <div className="font-body-md text-body-md text-on-surface leading-relaxed whitespace-pre-wrap">
            {message.content}
          </div>

          {sources.length > 0 && (
            <div className="pt-space-xs border-t border-surface-variant">
              <button
                type="button"
                onClick={() => setSourcesOpen((v) => !v)}
                className="flex items-center gap-1.5 font-label-md text-label-md text-secondary hover:text-primary transition-colors"
              >
                <span className="material-symbols-outlined text-[16px]">fact_check</span>
                <span>Fuentes ({sources.length})</span>
                <span className="material-symbols-outlined text-[16px]">
                  {sourcesOpen ? "expand_less" : "expand_more"}
                </span>
              </button>
              {sourcesOpen && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-sm mt-space-sm">
                  {sources.map((source, idx) => (
                    <button
                      type="button"
                      key={`${source.document_name}-${idx}`}
                      onClick={() => handleViewSource(source)}
                      title="Abrir el documento original"
                      className="bg-surface-container-low hover:bg-surface-container p-space-sm rounded-xl flex flex-col gap-0.5 text-left transition-colors cursor-pointer"
                    >
                      <span className="flex items-center gap-1 font-label-md text-label-md text-on-surface font-semibold truncate">
                        <span className="material-symbols-outlined text-[14px] flex-shrink-0">description</span>
                        {source.document_name ?? "Documento"}
                      </span>
                      <span className="font-body-sm text-body-sm text-outline">
                        {source.numero_articulo ? `Artículo ${source.numero_articulo}` : `Fragmento #${source.chunk_index}`}
                        {source.pagina_origen ? ` · pág. ${source.pagina_origen}` : ""}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              <ErrorBanner message={viewError} className="mt-space-sm" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

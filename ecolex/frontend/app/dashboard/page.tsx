"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ErrorBanner } from "@/components/ui/error-banner";
import { getErrorMessage } from "@/lib/errors";
import type { ApiEnvelope, ConversationItem, DocumentItem, PaginatedResponse } from "@/lib/types";

const STATUS_VARIANT = {
  ready: "ready",
  processing: "processing",
  error: "error",
} as const;

const STATUS_LABEL = {
  ready: "Listo",
  processing: "Procesando",
  error: "Error",
} as const;

export default function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const tenantName = user?.tenant_name ?? "Tu organización";

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [documentsTotal, setDocumentsTotal] = useState(0);
  const [readyCount, setReadyCount] = useState(0);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [conversationsTotal, setConversationsTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [docsRes, readyRes, convosRes] = await Promise.all([
          api.get<ApiEnvelope<PaginatedResponse<DocumentItem>>>("/api/v1/documents/", {
            params: { page_size: 5 },
          }),
          api.get<ApiEnvelope<PaginatedResponse<DocumentItem>>>("/api/v1/documents/", {
            params: { page_size: 1, status: "ready" },
          }),
          api.get<ApiEnvelope<PaginatedResponse<ConversationItem>>>("/api/v1/conversations/", {
            params: { page_size: 5 },
          }),
        ]);

        setDocuments(docsRes.data.data.items);
        setDocumentsTotal(docsRes.data.data.total);
        setReadyCount(readyRes.data.data.total);
        setConversations(convosRes.data.data.items);
        setConversationsTotal(convosRes.data.data.total);
      } catch (err) {
        setError(getErrorMessage(err, "No se pudo cargar el resumen del dashboard."));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="flex flex-col w-full gap-space-lg">
      <div className="flex flex-col">
        <div className="flex items-center gap-space-xs mb-space-xs">
          <span className="font-body-sm text-body-sm text-on-surface-variant font-medium">
            {tenantName}
          </span>
        </div>
        <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">
          Bienvenido{user?.email ? `, ${user.email}` : ""}
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant mt-0.5 capitalize">
          Rol: {user?.role ?? "—"}
        </p>
      </div>

      <ErrorBanner message={error} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex items-start justify-between">
          <div className="flex flex-col">
            <span className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">
              Documentos Listos
            </span>
            <span className="font-display-lg text-display-lg text-primary leading-none mt-space-xs">
              {loading ? "—" : readyCount}
            </span>
            <span className="font-body-sm text-body-sm text-on-surface-variant mt-1">
              de {documentsTotal} documentos totales
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-surface-container-low flex items-center justify-center text-primary">
            <span className="material-symbols-outlined text-[22px]">source</span>
          </div>
        </div>
        <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex items-start justify-between">
          <div className="flex flex-col">
            <span className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">
              Conversaciones
            </span>
            <span className="font-display-lg text-display-lg text-primary leading-none mt-space-xs">
              {loading ? "—" : conversationsTotal}
            </span>
            <span className="font-body-sm text-body-sm text-on-surface-variant mt-1">consultas jurídicas totales</span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-surface-container-low flex items-center justify-center text-primary">
            <span className="material-symbols-outlined text-[22px]">forum</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
        <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col">
          <div className="flex items-center justify-between pb-space-md">
            <h2 className="font-headline-sm text-headline-sm text-primary">Últimos Documentos</h2>
            <Link href="/documents" className="font-label-sm text-label-sm text-secondary hover:text-primary font-bold flex items-center gap-1">
              Ver todos
              <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
            </Link>
          </div>
          <div className="flex flex-col gap-space-sm">
            {!loading && !error && documents.length === 0 && (
              <p className="font-body-sm text-body-sm text-on-surface-variant">Sin documentos aún.</p>
            )}
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="p-space-sm rounded-xl bg-surface-container-low flex items-center justify-between gap-space-sm"
              >
                <div className="flex items-center gap-space-sm min-w-0">
                  <div className="w-9 h-9 rounded-lg bg-surface-container-highest flex items-center justify-center text-primary shrink-0">
                    <span className="material-symbols-outlined text-[20px]">description</span>
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="font-label-md text-label-md text-on-surface font-semibold truncate">
                      {doc.filename}
                    </span>
                    <span className="font-body-sm text-body-sm text-on-surface-variant truncate">
                      {doc.chunk_count} chunks
                    </span>
                  </div>
                </div>
                <Badge variant={STATUS_VARIANT[doc.status]}>{STATUS_LABEL[doc.status]}</Badge>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col">
          <div className="flex items-center justify-between pb-space-md">
            <h2 className="font-headline-sm text-headline-sm text-primary">Últimas Conversaciones</h2>
            <Link href="/chat" className="font-label-sm text-label-sm text-secondary hover:text-primary font-bold flex items-center gap-1">
              Ver todas
              <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
            </Link>
          </div>
          <div className="flex flex-col gap-space-sm">
            {!loading && !error && conversations.length === 0 && (
              <p className="font-body-sm text-body-sm text-on-surface-variant">Sin conversaciones aún.</p>
            )}
            {conversations.map((conv) => (
              <Link
                key={conv.id}
                href={`/chat/${conv.id}`}
                className="p-space-sm rounded-xl bg-surface-container-low hover:bg-surface-container transition-all flex items-center justify-between gap-space-sm"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="material-symbols-outlined text-[18px] text-secondary shrink-0">
                    chat_bubble_outline
                  </span>
                  <span className="font-title-md text-title-md text-on-surface truncate">
                    {conv.title ?? "Consulta sin título"}
                  </span>
                </div>
                <span className="font-label-sm text-label-sm text-on-surface-variant shrink-0">
                  {formatDate(conv.updated_at)}
                </span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

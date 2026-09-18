"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { getErrorMessage } from "@/lib/errors";
import { formatBytes, formatDate } from "@/lib/utils";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { UploadDropzone } from "@/components/documents/upload-dropzone";
import { DeleteDocumentDialog } from "@/components/documents/delete-document-dialog";
import type { ApiEnvelope, DocumentItem, PaginatedResponse } from "@/lib/types";

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

const POLL_INTERVAL_MS = 5000;

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const role = useAuthStore((state) => state.user?.role);
  const canUpload = role !== "viewer";
  const canDelete = role === "admin";
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadDocuments = useCallback(async () => {
    try {
      const res = await api.get<ApiEnvelope<PaginatedResponse<DocumentItem>>>("/api/v1/documents/", {
        params: { page_size: 50 },
      });
      setDocuments(res.data.data.items);
      setTotal(res.data.data.total);
      setLoadError(null);
    } catch (err) {
      setLoadError(getErrorMessage(err, "No se pudieron cargar los documentos."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Polling cada 5s mientras haya documentos en status=processing.
  useEffect(() => {
    const hasProcessing = documents.some((doc) => doc.status === "processing");
    if (hasProcessing && !pollRef.current) {
      pollRef.current = setInterval(loadDocuments, POLL_INTERVAL_MS);
    }
    if (!hasProcessing && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [documents, loadDocuments]);

  async function handleUpload(files: File[]) {
    setUploading(true);
    setUploadError(null);
    const failures: string[] = [];
    for (const file of files) {
      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("es_base_corpus", "false");
        await api.post("/api/v1/documents/upload", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      } catch (err) {
        failures.push(`${file.name}: ${getErrorMessage(err, "no se pudo subir el archivo.")}`);
      }
    }
    if (failures.length > 0) {
      setUploadError(failures.join(" "));
    }
    // Recargar siempre: los archivos subidos antes de un fallo deben aparecer en la tabla.
    await loadDocuments();
    setUploading(false);
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.delete(`/api/v1/documents/${deleteTarget.id}`);
      setDeleteTarget(null);
      await loadDocuments();
    } catch (err) {
      setDeleteError(getErrorMessage(err, "No se pudo eliminar el documento."));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col w-full gap-space-lg pb-space-xl">
      <div className="flex flex-col gap-space-xs">
        <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">
          Gestión de Documentos
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant max-w-2xl">
          Suba licencias, resoluciones y normativa propia para extender la base de conocimiento del
          agente conversacional.
        </p>
      </div>

      {canUpload && <UploadDropzone onFiles={handleUpload} disabled={uploading} />}
      <ErrorBanner message={uploadError} />
      <ErrorBanner message={loadError} />
      {uploading && (
        <p className="font-label-md text-label-md text-secondary flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>
          Subiendo documento(s)...
        </p>
      )}

      <div className="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden flex flex-col">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nombre</TableHead>
              <TableHead>Tipo</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Fecha</TableHead>
              <TableHead>Fragmentos</TableHead>
              {canDelete && <TableHead className="text-right">Acciones</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {!loading && !loadError && documents.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-on-surface-variant py-space-xl">
                  {canUpload ? "Aún no hay documentos. Sube el primero arriba." : "Aún no hay documentos."}
                </TableCell>
              </TableRow>
            )}
            {documents.map((doc) => (
              <TableRow key={doc.id}>
                <TableCell>
                  <div className="flex items-center gap-space-sm">
                    <div className="w-9 h-9 rounded-lg bg-surface-container-highest flex items-center justify-center text-primary shrink-0">
                      <span className="material-symbols-outlined text-[20px]">
                        {doc.file_type === "pdf" ? "picture_as_pdf" : "description"}
                      </span>
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="font-label-lg text-label-lg text-primary font-semibold truncate">
                        {doc.filename}
                      </span>
                      <span className="text-outline text-[11px] font-medium">
                        {formatBytes(doc.file_size_bytes)}
                        {doc.status === "error" && doc.error_message && (
                          <span className="text-error"> • {doc.error_message}</span>
                        )}
                      </span>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="whitespace-nowrap uppercase text-label-sm font-label-sm text-on-surface-variant">
                  {doc.file_type}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <Badge variant={STATUS_VARIANT[doc.status]}>
                    {doc.status === "processing" && (
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                    )}
                    {STATUS_LABEL[doc.status]}
                  </Badge>
                </TableCell>
                <TableCell className="whitespace-nowrap text-on-surface-variant font-label-md text-label-md">
                  {formatDate(doc.created_at)}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <span className="font-label-md text-label-md font-semibold text-primary">
                    {doc.chunk_count}
                  </span>
                </TableCell>
                {canDelete && (
                  <TableCell className="whitespace-nowrap text-right">
                    <button
                      onClick={() => {
                        setDeleteError(null);
                        setDeleteTarget(doc);
                      }}
                      className="p-1.5 rounded-lg text-error hover:bg-error-container hover:text-on-error-container transition-colors"
                      title="Eliminar documento"
                    >
                      <span className="material-symbols-outlined text-[19px]">delete</span>
                    </button>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="bg-surface-container-low px-space-lg py-space-md font-body-sm text-body-sm text-on-surface-variant">
          Mostrando {documents.length} de {total} documentos
        </div>
      </div>

      {deleteTarget && (
        <DeleteDocumentDialog
          open={!!deleteTarget}
          onOpenChange={(open) => !open && setDeleteTarget(null)}
          filename={deleteTarget.filename}
          onConfirm={handleDelete}
          loading={deleting}
          error={deleteError}
        />
      )}
    </div>
  );
}

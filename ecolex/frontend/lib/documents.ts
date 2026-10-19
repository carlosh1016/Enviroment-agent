import { api } from "./api";

export const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt", ".mhtml", ".mht", ".html", ".htm", ".xlsx", ".csv"];
export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50MB, igual al limite del backend

export function validateFile(file: File): string | null {
  const extension = "." + (file.name.split(".").pop() ?? "").toLowerCase();
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return `Extensión no soportada (${extension}). Solo se permiten PDF, DOCX, TXT, MHTML, HTML, XLSX o CSV.`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return "El archivo supera el tamaño máximo permitido de 50MB.";
  }
  return null;
}

/**
 * Abre el archivo original de un documento (PDF/DOCX/TXT) en una pestaña nueva, autenticado
 * via el mismo cliente axios que el resto de la app (Bearer token + refresh automatico).
 * `page` salta a la pagina aproximada del fragmento citado (soportado por el visor nativo de
 * PDF de Chrome/Firefox/Edge via el fragmento #page=N; si el navegador lo ignora, simplemente
 * abre en la pagina 1 -- no es un fallo funcional).
 *
 * El object URL no se revoca de inmediato: el navegador necesita tiempo para cargarlo en la
 * pestaña nueva. Se libera solo cuando esta pestaña se recarga o se cierra, lo cual es
 * aceptable para un visor ocasional y no amerita un manejo de ciclo de vida mas complejo.
 */
export async function openDocumentFile(documentId: string, page?: number | null): Promise<void> {
  const response = await api.get(`/api/v1/documents/${documentId}/file`, { responseType: "blob" });
  const blobUrl = URL.createObjectURL(response.data as Blob);
  window.open(page ? `${blobUrl}#page=${page}` : blobUrl, "_blank", "noopener,noreferrer");
}

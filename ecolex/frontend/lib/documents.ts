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
 * IMPORTANTE: usa un <a target="_blank"> + click() programatico, NO `window.open()`. Se probo
 * primero con `window.open()` (incluso abriendolo de forma sincronica antes del `await`, para
 * que el navegador lo reconociera como resultado directo del clic) y de todas formas se seguia
 * bloqueando como popup en produccion. La navegacion via un <a> con target="_blank" no la
 * tratan como popup los bloqueadores, aun llamando `.click()` despues de un `await` -- es la
 * misma tecnica que usan FileSaver.js y librerias similares para "descargar/abrir un blob
 * obtenido por fetch".
 *
 * El object URL no se revoca de inmediato: el navegador necesita tiempo para cargarlo en la
 * pestaña nueva. Se libera solo cuando esta pestaña se recarga o se cierra, lo cual es
 * aceptable para un visor ocasional y no amerita un manejo de ciclo de vida mas complejo.
 */
export async function openDocumentFile(documentId: string, page?: number | null): Promise<void> {
  const response = await api.get(`/api/v1/documents/${documentId}/file`, { responseType: "blob" });
  const blobUrl = URL.createObjectURL(response.data as Blob);
  const link = document.createElement("a");
  link.href = page ? `${blobUrl}#page=${page}` : blobUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.click();
}

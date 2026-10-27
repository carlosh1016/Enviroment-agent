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
 * IMPORTANTE: la pestaña se abre ANTES de pedir el archivo (sincronico, dentro del mismo clic
 * del usuario) y se navega a la URL real recien cuando llega la respuesta -- si se abre
 * `window.open` despues de un `await`, el navegador ya no lo reconoce como resultado directo
 * de un clic y lo bloquea en silencio como popup (confirmado en vivo: no tiraba ningun error,
 * simplemente no pasaba nada).
 *
 * El object URL no se revoca de inmediato: el navegador necesita tiempo para cargarlo en la
 * pestaña nueva. Se libera solo cuando esta pestaña se recarga o se cierra, lo cual es
 * aceptable para un visor ocasional y no amerita un manejo de ciclo de vida mas complejo.
 */
export async function openDocumentFile(documentId: string, page?: number | null): Promise<void> {
  const newTab = window.open();
  if (!newTab) {
    throw new Error("El navegador bloqueó la ventana nueva. Habilita las ventanas emergentes para este sitio.");
  }
  try {
    const response = await api.get(`/api/v1/documents/${documentId}/file`, { responseType: "blob" });
    const blobUrl = URL.createObjectURL(response.data as Blob);
    newTab.location.href = page ? `${blobUrl}#page=${page}` : blobUrl;
  } catch (err) {
    newTab.close();
    throw err;
  }
}

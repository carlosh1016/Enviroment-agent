export const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt"];
export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10MB, igual al limite del backend

export function validateFile(file: File): string | null {
  const extension = "." + (file.name.split(".").pop() ?? "").toLowerCase();
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return `Extensión no soportada (${extension}). Solo se permiten PDF, DOCX o TXT.`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return "El archivo supera el tamaño máximo permitido de 10MB.";
  }
  return null;
}

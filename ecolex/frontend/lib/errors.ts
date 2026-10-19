import axios from "axios";

export const MSG_VALIDATION = "Revisa los datos ingresados e intenta de nuevo.";
export const MSG_RATE_LIMIT = "Demasiados intentos. Espera 1 minuto e intenta de nuevo.";
export const MSG_NETWORK = "No se pudo conectar con el servidor. Revisa tu conexión e intenta de nuevo.";
export const MSG_GENERIC = "Ocurrió un error inesperado. Intenta de nuevo en unos minutos.";
export const MSG_CHAT_FAILED =
  "El asistente no pudo responder. Tu pregunta fue guardada, puedes intentar de nuevo.";

function _messageForStatus(status: number, serverMessage: string | null, fallback: string): string {
  if (status === 422) return serverMessage ?? MSG_VALIDATION;
  if (status === 429) return MSG_RATE_LIMIT;
  if (status === 403) return serverMessage ?? "No tienes permisos para realizar esta acción.";
  if (status === 404) return serverMessage ?? "No se encontró el recurso solicitado.";
  if (status >= 500) return fallback;
  return serverMessage ?? fallback;
}

/**
 * Traduce un error de axios a un mensaje visible para el usuario, de forma
 * consistente entre pantallas (422, 429, 403, 404, 5xx y red caida).
 * `fallback` se usa para 5xx y errores no HTTP, para que cada pantalla diga
 * que accion fallo.
 */
export function getErrorMessage(err: unknown, fallback: string = MSG_GENERIC): string {
  if (!axios.isAxiosError(err)) return fallback;
  if (!err.response) return MSG_NETWORK;

  const { status, data } = err.response;
  const serverMessage = typeof data?.message === "string" ? data.message : null;
  return _messageForStatus(status, serverMessage, fallback);
}

/**
 * Como getErrorMessage, pero para requests hechos con `responseType: "blob"` (ej. descargar un
 * PDF): el body de un error TAMBIEN llega como Blob, no como el envelope {success,message,data}
 * ya parseado, asi que un mensaje especifico del backend (ej. "Se necesitan al menos 2 mensajes
 * para generar un informe") se perderia detras del mensaje generico por status code. Lee el
 * Blob como texto/JSON antes de delegar a la misma logica de getErrorMessage.
 */
export async function getBlobErrorMessage(err: unknown, fallback: string = MSG_GENERIC): Promise<string> {
  if (!axios.isAxiosError(err)) return fallback;
  if (!err.response) return MSG_NETWORK;

  const { status, data } = err.response;
  let serverMessage: string | null = null;
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text());
      serverMessage = typeof parsed?.message === "string" ? parsed.message : null;
    } catch {
      // El body no era JSON (ej. un 500 con HTML de error) -- sigue con serverMessage=null.
    }
  }
  return _messageForStatus(status, serverMessage, fallback);
}

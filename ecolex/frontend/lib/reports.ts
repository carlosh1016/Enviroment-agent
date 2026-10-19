import { api } from "./api";

/**
 * Pide el informe PDF de cumplimiento de una conversacion
 * (POST /api/v1/reports/conversations/{id}) y dispara su descarga en el navegador.
 *
 * El nombre de archivo se toma del header Content-Disposition que arma el backend
 * (`informe_<id>_<fecha>.pdf`); si por algo no viene, cae a un nombre generico.
 *
 * Si falla, propaga el error de axios tal cual (responseType "blob", asi que el body del
 * error tambien es un Blob) para que el llamador lo traduzca con getBlobErrorMessage.
 */
export async function downloadConversationReport(conversationId: string): Promise<void> {
  const response = await api.post(
    `/api/v1/reports/conversations/${conversationId}`,
    {},
    { responseType: "blob" }
  );

  const disposition = response.headers["content-disposition"] as string | undefined;
  const filename = disposition?.match(/filename="?([^";]+)"?/)?.[1] ?? `informe_${conversationId.slice(0, 8)}.pdf`;

  const blobUrl = URL.createObjectURL(response.data as Blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(blobUrl);
}

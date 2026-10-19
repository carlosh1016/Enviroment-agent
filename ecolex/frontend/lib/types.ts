export interface Tenant {
  id: string;
  name: string;
  slug: string;
}

/**
 * Shape real de GET /auth/me. El backend no expone full_name, pero si
 * tenant_name (via JOIN con tenants) -- es la fuente de verdad para mostrar
 * el nombre de la empresa en el sidebar y el dashboard.
 */
export interface CurrentUser {
  id: string;
  tenant_id: string;
  tenant_name: string;
  email: string;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
}

export type DocumentStatus = "processing" | "ready" | "error";

export interface DocumentItem {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: DocumentStatus;
  chunk_count: number;
  error_message?: string | null;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ConversationItem {
  id: string;
  user_id: string | null;
  // Email del dueno de la conversacion. Para un admin viendo las conversaciones de todo el
  // tenant, permite saber de quien es cada una (ver TestAdminAuditorView en el backend).
  user_email?: string | null;
  title?: string | null;
  created_at: string;
  updated_at: string;
}

export type MessageRole = "user" | "assistant";

export interface SourceChunk {
  document_id: string;
  // Null en mensajes guardados antes de que el backend empezara a incluirlo.
  document_name: string | null;
  chunk_index: number;
  score: number;
  numero_articulo?: string | null;
  pagina_origen?: number | null;
}

export interface MessageItem {
  id: string;
  role: MessageRole;
  content: string;
  source_chunks?: SourceChunk[] | null;
  created_at: string;
}

export type UserRoleValue = "admin" | "analyst" | "viewer";

/** Usuario del tenant tal como lo devuelve GET/POST/PATCH /api/v1/users/. */
export interface ManagedUser {
  id: string;
  email: string;
  role: UserRoleValue;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

/** GET /api/v1/stats/dashboard: agregados para las graficas del dashboard. */
export interface DayActivity {
  date: string;
  conversations: number;
  messages: number;
}

export interface CitedDocument {
  document_id: string;
  document_name: string;
  citations: number;
}

export interface DashboardStats {
  documents_by_status: Record<string, number>;
  documents_by_type: Record<string, number>;
  activity_last_14_days: DayActivity[];
  top_cited_documents: CitedDocument[];
}

export interface ApiEnvelope<T> {
  success: boolean;
  message?: string;
  data: T;
}

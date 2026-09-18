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
  title?: string | null;
  created_at: string;
  updated_at: string;
}

export type MessageRole = "user" | "assistant";

export interface SourceChunk {
  document_name: string;
  chunk_index: number;
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
  created_at: string;
}

export interface ApiEnvelope<T> {
  success: boolean;
  message?: string;
  data: T;
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import type { ApiEnvelope, ConversationItem, PaginatedResponse } from "@/lib/types";

const CONVERSATIONS_CHANGED_EVENT = "ecolex:conversations-changed";

/** Avisa a la lista de conversaciones (que vive en el layout de /chat) que debe recargarse. */
export function notifyConversationsChanged() {
  window.dispatchEvent(new Event(CONVERSATIONS_CHANGED_EVENT));
}

export function useConversations() {
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const res = await api.get<ApiEnvelope<PaginatedResponse<ConversationItem>>>(
        "/api/v1/conversations/",
        { params: { page_size: 50 } }
      );
      setConversations(res.data.data.items);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudieron cargar las conversaciones."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    window.addEventListener(CONVERSATIONS_CHANGED_EVENT, reload);
    return () => window.removeEventListener(CONVERSATIONS_CHANGED_EVENT, reload);
  }, [reload]);

  async function createConversation() {
    setCreating(true);
    setError(null);
    try {
      const res = await api.post<ApiEnvelope<ConversationItem>>("/api/v1/conversations/", {});
      await reload();
      router.push(`/chat/${res.data.data.id}`);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo crear la conversación."));
    } finally {
      setCreating(false);
    }
  }

  return { conversations, loading, creating, error, reload, createConversation };
}

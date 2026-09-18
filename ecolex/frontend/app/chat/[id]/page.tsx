"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getErrorMessage, MSG_CHAT_FAILED } from "@/lib/errors";
import { notifyConversationsChanged } from "@/lib/hooks/use-conversations";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ChatInput } from "@/components/chat/chat-input";
import { ErrorBanner } from "@/components/ui/error-banner";
import type { ApiEnvelope, MessageItem } from "@/lib/types";

const TITLE_MAX_CHARS = 50;

export default function ConversationPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const conversationId = params.id;

  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    setChatError(null);
    api
      .get<ApiEnvelope<MessageItem[]>>(`/api/v1/conversations/${conversationId}/messages`)
      .then((res) => setMessages(res.data.data))
      .catch((err) => setLoadError(getErrorMessage(err, "No se pudo cargar la conversación.")))
      .finally(() => setLoading(false));
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, chatError]);

  /** Devuelve true si el mensaje se envio y respondio bien (el input solo se limpia en ese caso). */
  async function handleSend(content: string): Promise<boolean> {
    const isFirstMessage = !loading && !loadError && messages.length === 0;
    setChatError(null);

    const optimisticUser: MessageItem = {
      id: `optimistic-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);
    setSending(true);

    if (isFirstMessage) {
      api
        .patch(`/api/v1/conversations/${conversationId}`, { title: content.slice(0, TITLE_MAX_CHARS) })
        .then(() => notifyConversationsChanged())
        .catch((err) => console.error("No se pudo actualizar el título de la conversación", err));
    }

    try {
      const res = await api.post<ApiEnvelope<MessageItem>>(
        `/api/v1/conversations/${conversationId}/messages`,
        { content }
      );
      setMessages((prev) => [...prev, res.data.data]);
      return true;
    } catch (err) {
      // El backend guarda la pregunta antes de llamar al RAG, asi que el mensaje optimista se conserva.
      setChatError(getErrorMessage(err, MSG_CHAT_FAILED));
      return false;
    } finally {
      setSending(false);
    }
  }

  async function handleDeleteConversation() {
    if (!confirm("¿Eliminar esta conversación y todos sus mensajes?")) return;
    setDeleteError(null);
    try {
      await api.delete(`/api/v1/conversations/${conversationId}`);
      notifyConversationsChanged();
      router.push("/chat");
    } catch (err) {
      setDeleteError(getErrorMessage(err, "No se pudo eliminar la conversación."));
    }
  }

  return (
    <>
      <header className="p-space-md bg-surface-container-lowest flex items-center justify-between gap-space-sm border-b border-surface-variant">
        <div className="flex items-center gap-space-xs">
          <span className="material-symbols-outlined text-secondary text-[22px]">gavel</span>
          <h1 className="font-headline-sm text-headline-sm text-primary tracking-tight">
            Consulta Jurídica
          </h1>
        </div>
        <button
          type="button"
          onClick={handleDeleteConversation}
          className="p-space-xs text-on-surface-variant hover:text-error hover:bg-surface-container-low rounded-xl transition-colors"
          title="Eliminar conversación"
        >
          <span className="material-symbols-outlined text-[20px]">delete_sweep</span>
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-space-lg flex flex-col gap-space-lg bg-surface">
        <ErrorBanner message={deleteError} />
        <ErrorBanner message={loadError} />
        {loading && <p className="font-body-sm text-body-sm text-on-surface-variant">Cargando...</p>}
        {!loading && !loadError && messages.length === 0 && (
          <p className="font-body-sm text-body-sm text-on-surface-variant">
            Escribe tu primera pregunta sobre normativa ambiental abajo.
          </p>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {sending && (
          <div className="flex items-center gap-2 text-on-surface-variant font-body-sm text-body-sm self-start">
            <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>
            Ecolex está redactando la respuesta...
          </div>
        )}
        <ErrorBanner message={chatError} className="self-start" />
        <div ref={bottomRef} />
      </div>

      <ChatInput onSend={handleSend} disabled={sending || !!loadError} />
    </>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { formatDate } from "@/lib/utils";
import { ErrorBanner } from "@/components/ui/error-banner";
import type { ConversationItem } from "@/lib/types";

interface ConversationListProps {
  conversations: ConversationItem[];
  loading: boolean;
  creating: boolean;
  error: string | null;
  onCreate: () => void;
}

export function ConversationList({ conversations, loading, creating, error, onCreate }: ConversationListProps) {
  const pathname = usePathname();

  return (
    <aside className="xl:col-span-4 2xl:col-span-3 flex flex-col gap-space-md bg-surface-container-low rounded-xl p-space-md shadow-sm">
      <button
        type="button"
        onClick={onCreate}
        disabled={creating}
        className="w-full flex items-center justify-center gap-space-xs py-space-sm px-space-md bg-primary text-on-primary rounded-xl font-label-lg text-label-lg shadow-md hover:bg-primary-container transition-all disabled:opacity-60"
      >
        <span className="material-symbols-outlined text-[20px]">add</span>
        <span>Nueva Consulta Jurídica</span>
      </button>

      <ErrorBanner message={error} />

      <div className="flex flex-col gap-space-xs overflow-y-auto max-h-[calc(100vh-14rem)] pr-space-xs">
        {loading && (
          <p className="font-body-sm text-body-sm text-on-surface-variant px-space-xs">Cargando...</p>
        )}
        {!loading && !error && conversations.length === 0 && (
          <p className="font-body-sm text-body-sm text-on-surface-variant px-space-xs">
            Aún no tienes conversaciones. Crea la primera.
          </p>
        )}
        {conversations.map((conv) => {
          const active = pathname === `/chat/${conv.id}`;
          return (
            <Link
              key={conv.id}
              href={`/chat/${conv.id}`}
              className={`flex flex-col gap-1 p-space-sm rounded-xl transition-colors ${
                active ? "bg-surface-container-lowest shadow-sm" : "hover:bg-surface-container"
              }`}
            >
              <span
                className={`font-label-lg text-label-lg truncate ${
                  active ? "text-primary font-semibold" : "text-on-surface font-medium"
                }`}
              >
                {conv.title ?? "Consulta sin título"}
              </span>
              <span className="font-label-sm text-label-sm text-outline">{formatDate(conv.updated_at)}</span>
            </Link>
          );
        })}
      </div>
    </aside>
  );
}

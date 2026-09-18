"use client";

import { AppShell } from "@/components/layout/app-shell";
import { ConversationList } from "@/components/chat/conversation-list";
import { useConversations } from "@/lib/hooks/use-conversations";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { conversations, loading, creating, error, createConversation } = useConversations();

  return (
    <AppShell>
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-lg w-full min-h-[calc(100vh-6.5rem)]">
        <ConversationList
          conversations={conversations}
          loading={loading}
          creating={creating}
          error={error}
          onCreate={createConversation}
        />
        <section className="xl:col-span-8 2xl:col-span-9 flex flex-col bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
          {children}
        </section>
      </div>
    </AppShell>
  );
}

"use client";

import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  onSend: (content: string) => Promise<boolean>;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");

  async function handleSubmit() {
    const content = value.trim();
    if (!content || disabled) return;
    // El texto solo se borra si el envio salio bien: si falla, el usuario puede reintentar.
    const sent = await onSend(content);
    if (sent) setValue("");
  }

  return (
    <footer className="p-space-md bg-surface-container-lowest shadow-lg flex flex-col gap-space-xs">
      <div className="relative flex items-end gap-space-xs p-space-xs bg-surface-container-low rounded-2xl focus-within:ring-2 focus-within:ring-secondary transition-all">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder="Escriba su consulta jurídica ambiental..."
          rows={2}
          disabled={disabled}
        />
        <button
          type="button"
          aria-label="Enviar consulta"
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className="w-10 h-10 rounded-xl bg-primary text-on-primary flex items-center justify-center shadow-md hover:bg-primary-container transition-all active:scale-95 disabled:opacity-50 mb-1 mr-1 shrink-0"
        >
          <span className="material-symbols-outlined text-[20px] text-secondary-fixed">
            {disabled ? "hourglass_top" : "send"}
          </span>
        </button>
      </div>
      <div className="flex items-center justify-center gap-1 pt-1">
        <span className="material-symbols-outlined text-[14px] text-outline">verified</span>
        <span className="font-label-sm text-label-sm text-outline text-center">
          Ecolex cita normativa vigente. Verifique siempre con la fuente oficial (ANLA, CAR o
          MinAmbiente).
        </span>
      </div>
    </footer>
  );
}

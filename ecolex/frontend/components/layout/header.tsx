"use client";

import { useAuthStore } from "@/lib/store";

export function Header() {
  const user = useAuthStore((state) => state.user);
  const initials = user?.email?.slice(0, 2).toUpperCase() ?? "??";

  return (
    <header className="fixed top-0 left-64 right-0 h-16 bg-surface-container-lowest/90 backdrop-blur-xl z-40 px-space-lg flex items-center justify-between shadow-[0_1px_8px_rgba(27,67,50,0.05)]">
      <div className="flex items-center gap-space-lg flex-1 max-w-xl">
        <div className="relative w-full max-w-md">
          <span className="material-symbols-outlined absolute left-space-md top-1/2 -translate-y-1/2 text-outline text-[18px]">
            search
          </span>
          <input
            className="w-full pl-10 pr-space-md py-space-xs bg-surface-container-low rounded-xl font-body-sm text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:bg-surface-container-lowest focus:ring-1 focus:ring-secondary transition-all"
            placeholder="Buscar normativa ambiental..."
            type="text"
          />
        </div>
      </div>
      <div className="flex items-center gap-space-md">
        <button
          aria-label="Notificaciones"
          type="button"
          className="relative p-space-sm rounded-xl text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface transition-colors"
        >
          <span className="material-symbols-outlined text-[22px]">notifications</span>
        </button>
        <div className="h-6 w-px bg-surface-container-highest" />
        <div className="flex items-center gap-space-sm pl-space-xs">
          <div className="w-8 h-8 rounded-full bg-primary-container text-on-primary flex items-center justify-center font-label-sm text-label-sm font-bold ring-1 ring-surface-container-high">
            {initials}
          </div>
          <div className="hidden md:flex flex-col text-left">
            <span className="font-label-md text-label-md text-on-surface font-semibold leading-tight">
              {user?.email ?? "—"}
            </span>
            <span className="font-label-sm text-label-sm text-on-surface-variant leading-tight capitalize">
              {user?.role ?? ""}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}

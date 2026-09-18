"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { useHydrated } from "@/lib/hooks/use-hydrated";
import { api } from "@/lib/api";
import type { ApiEnvelope, CurrentUser } from "@/lib/types";
import { Sidebar } from "./sidebar";
import { Header } from "./header";

/**
 * Envuelve las rutas protegidas: exige un access token en el store (persistido
 * en localStorage via zustand/persist) y redirige a /login si no existe.
 * Si hay token pero no hay datos de usuario en cache (ej. refresh de pagina),
 * los recupera de GET /auth/me antes de renderizar el contenido.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const hydrated = useHydrated();
  const accessToken = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Esperar a que zustand/persist termine de leer localStorage antes de
    // decidir si hay sesion -- si no, un F5 en una ruta protegida rebota a
    // /login aunque el usuario siga autenticado.
    if (!hydrated) return;

    if (!accessToken) {
      router.replace("/login");
      return;
    }
    if (user) {
      setReady(true);
      return;
    }
    api
      .get<ApiEnvelope<CurrentUser>>("/auth/me")
      .then((res) => {
        setUser(res.data.data);
        setReady(true);
      })
      .catch(() => {
        router.replace("/login");
      });
  }, [hydrated, accessToken, user, router, setUser]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface">
        <span className="material-symbols-outlined text-primary text-[32px] animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  return (
    <div className="bg-surface min-h-screen">
      <Sidebar />
      <div className="pl-64 flex flex-col min-h-screen bg-surface">
        <Header />
        <main className="w-full pt-16 px-space-lg py-space-lg flex-1 bg-surface">{children}</main>
      </div>
    </div>
  );
}

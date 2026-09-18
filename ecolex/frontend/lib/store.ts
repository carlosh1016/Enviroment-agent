import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CurrentUser } from "./types";

interface AuthState {
  accessToken: string | null;
  user: CurrentUser | null;
  setSession: (accessToken: string, user?: CurrentUser | null) => void;
  setUser: (user: CurrentUser) => void;
  clearSession: () => void;
}

/**
 * El refresh token vive solo en la cookie httpOnly que maneja el backend
 * (nunca se toca desde el frontend). Solo persistimos el access token y el
 * usuario actual (incluido `tenant_name`, de GET /auth/me) para que la
 * sesion sobreviva un refresh de pagina.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      user: null,
      setSession: (accessToken, user = null) => set({ accessToken, user }),
      setUser: (user) => set({ user }),
      clearSession: () => set({ accessToken: null, user: null }),
    }),
    {
      name: "ecolex-auth",
    }
  )
);

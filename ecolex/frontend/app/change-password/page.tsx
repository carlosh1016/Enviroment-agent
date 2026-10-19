"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { getErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBanner } from "@/components/ui/error-banner";

export default function ChangePasswordPage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const clearSession = useAuthStore((state) => state.clearSession);
  const isForced = user?.must_change_password ?? false;

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("Las contraseñas nuevas no coinciden.");
      return;
    }

    setLoading(true);
    try {
      await api.patch("/auth/me/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      if (user) setUser({ ...user, must_change_password: false });
      router.push("/dashboard");
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        setError("La contraseña actual no es correcta.");
      } else {
        setError(getErrorMessage(err, "No se pudo cambiar la contraseña."));
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    try {
      await api.post("/auth/logout");
    } catch {
      // La sesion local se cierra igual aunque el servidor no responda.
    } finally {
      clearSession();
      router.push("/login");
    }
  }

  return (
    <div className="flex flex-col w-full items-center">
      <div className="w-full max-w-lg flex flex-col gap-space-lg">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">
            {isForced ? "Define tu nueva contraseña" : "Cambiar contraseña"}
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant mt-0.5">
            {isForced
              ? "Tu administrador creó esta cuenta con una contraseña temporal. Por seguridad, debes definir una propia antes de continuar."
              : "Define una nueva contraseña de acceso a Ecolex."}
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-md"
        >
          <div className="space-y-1">
            <Label>{isForced ? "Contraseña temporal" : "Contraseña actual"}</Label>
            <Input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <Label>Nueva contraseña</Label>
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              minLength={8}
              required
            />
          </div>
          <div className="space-y-1">
            <Label>Confirmar nueva contraseña</Label>
            <Input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              minLength={8}
              required
            />
          </div>

          <ErrorBanner message={error} />

          <Button type="submit" disabled={loading} className="w-full mt-space-sm">
            <span>{loading ? "Guardando..." : "Guardar y continuar"}</span>
          </Button>

          {isForced && (
            <button
              type="button"
              onClick={handleLogout}
              className="text-center font-label-md text-label-md text-on-surface-variant hover:text-error mt-space-xs"
            >
              Cerrar sesión
            </button>
          )}
        </form>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import axios from "axios";
import { api } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBanner } from "@/components/ui/error-banner";

export default function SettingsPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

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
      setSuccess("Contraseña actualizada exitosamente.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
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

  return (
    <div className="flex flex-col w-full gap-space-lg max-w-lg">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">Mi Cuenta</h1>
        <p className="font-body-md text-body-md text-on-surface-variant mt-0.5">
          Cambia tu contraseña de acceso a Ecolex.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-md"
      >
        <div className="space-y-1">
          <Label>Contraseña actual</Label>
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
        {success && (
          <p
            role="status"
            className="font-body-sm text-body-sm text-secondary bg-secondary-container/40 rounded-lg px-3 py-2"
          >
            {success}
          </p>
        )}

        <Button type="submit" disabled={loading} className="w-full mt-space-sm">
          <span>{loading ? "Guardando..." : "Cambiar contraseña"}</span>
        </Button>
      </form>
    </div>
  );
}

"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EcolexMark } from "@/components/ecolex/logo";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: newPassword });
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (err) {
      setError(getErrorMessage(err, "El enlace no es válido o ya expiró. Solicita uno nuevo."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-surface flex items-center justify-center p-space-md">
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-2xl p-space-xl flex flex-col gap-space-md">
        <div className="flex items-center gap-space-sm mb-space-sm">
          <div className="w-11 h-11 rounded-lg bg-primary-container p-1.5 shadow-md flex items-center justify-center">
            <EcolexMark className="w-full h-full object-contain" />
          </div>
          <div className="flex flex-col">
            <span className="font-headline-sm text-headline-sm text-primary tracking-tight leading-none">
              ECOLEX
            </span>
            <span className="font-label-sm text-label-sm text-outline tracking-wider uppercase mt-1">
              Restablecer contraseña
            </span>
          </div>
        </div>

        {!token && (
          <ErrorBanner message="Este enlace no incluye un token válido. Solicita uno nuevo desde el inicio de sesión." />
        )}

        {success ? (
          <p role="status" className="font-body-md text-body-md text-secondary bg-secondary-container/40 rounded-lg px-3 py-3">
            Contraseña actualizada exitosamente. Te estamos redirigiendo al inicio de sesión...
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-space-md">
            <div className="space-y-1">
              <Label>Nueva contraseña</Label>
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={8}
                required
                disabled={!token}
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
                disabled={!token}
              />
            </div>

            <ErrorBanner message={error} />

            <Button type="submit" disabled={loading || !token} className="w-full mt-space-sm">
              <span>{loading ? "Guardando..." : "Restablecer contraseña"}</span>
            </Button>
          </form>
        )}

        <Link
          href="/login"
          className="text-center font-label-md text-label-md text-secondary hover:text-primary mt-space-xs"
        >
          Volver a iniciar sesión
        </Link>
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams requiere un limite Suspense en el App Router.
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}

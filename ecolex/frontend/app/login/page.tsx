"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { slugify } from "@/lib/utils";
import { getErrorMessage } from "@/lib/errors";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EcolexMark } from "@/components/ecolex/logo";
import type { ApiEnvelope } from "@/lib/types";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const setSession = useAuthStore((state) => state.setSession);

  const [mode, setMode] = useState<Mode>("login");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const slugPreview = slugify(companyName);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.post<ApiEnvelope<{ access_token: string }>>("/auth/login", {
        email,
        password,
      });
      setSession(res.data.data.access_token);
      router.push("/dashboard");
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        setError("Credenciales inválidas. Verifica tu correo y contraseña.");
      } else {
        setError(getErrorMessage(err, "No se pudo iniciar sesión. Intenta de nuevo."));
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const tenant_slug = slugify(companyName);
      await api.post("/auth/register", {
        tenant_name: companyName,
        tenant_slug,
        admin_email: email,
        admin_password: password,
      });

      const loginRes = await api.post<ApiEnvelope<{ access_token: string }>>("/auth/login", {
        email,
        password,
        tenant_slug,
      });
      setSession(loginRes.data.data.access_token);
      router.push("/dashboard");
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        setError("Ya existe una organización con ese nombre. Si ya tienes cuenta, inicia sesión.");
      } else {
        setError(getErrorMessage(err, "No se pudo completar el registro. Intenta de nuevo."));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-surface flex items-center justify-center p-space-md">
      <div className="w-full max-w-5xl flex flex-col lg:flex-row rounded-xl overflow-hidden shadow-2xl bg-surface-container-lowest">
        {/* Columna izquierda: branding editorial */}
        <div className="w-full lg:w-7/12 relative flex flex-col justify-between p-space-lg lg:p-space-xl bg-primary-container text-on-primary overflow-hidden">
          <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-secondary-container/10 blur-3xl pointer-events-none" />
          <div className="absolute -bottom-20 -right-20 w-96 h-96 rounded-full bg-tertiary-fixed/15 blur-3xl pointer-events-none" />

          <div className="relative z-10 flex items-center gap-space-sm mb-space-xl">
            <div className="w-11 h-11 rounded-lg bg-surface-container-lowest p-1.5 shadow-md flex items-center justify-center">
              <EcolexMark className="w-full h-full object-contain" />
            </div>
            <div className="flex flex-col">
              <span className="font-headline-sm text-headline-sm tracking-tight text-surface-container-lowest leading-none">
                ECOLEX
              </span>
              <span className="font-label-sm text-label-sm text-secondary-fixed tracking-wider uppercase mt-1">
                Jurisprudencia Verde
              </span>
            </div>
          </div>

          <div className="relative z-10 flex flex-col my-auto space-y-space-lg">
            <div>
              <h1 className="font-headline-lg text-headline-lg text-surface-container-lowest tracking-tight leading-tight mb-space-sm">
                Normativa ambiental colombiana,{" "}
                <span className="text-secondary-fixed">siempre a tu alcance.</span>
              </h1>
              <p className="font-body-md text-body-md text-on-primary-container leading-relaxed">
                Consulta instantánea sobre licencias ambientales, decretos del MinAmbiente y
                jurisprudencia vinculante, con citación jurídica exacta.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 pt-space-xs">
              <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-tertiary-container/80 text-secondary-fixed font-label-md text-label-md shadow-sm">
                <span className="material-symbols-outlined text-body-md">verified</span>
                Normativa ambiental colombiana pre-cargada
              </div>
              <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-tertiary-container/80 text-secondary-fixed font-label-md text-label-md shadow-sm">
                <span className="material-symbols-outlined text-body-md">auto_awesome</span>
                RAG con citación exacta
              </div>
            </div>
          </div>

          <div className="relative z-10 mt-space-xl p-space-md rounded-xl bg-surface-container-lowest/10 backdrop-blur-md shadow-md">
            <div className="flex items-start gap-3">
              <span className="material-symbols-outlined text-secondary-fixed text-headline-md leading-none">
                format_quote
              </span>
              <p className="font-body-sm text-body-sm text-surface-container-high italic leading-snug">
                Ecolex redujo nuestros tiempos de revisión normativa frente a requerimientos
                ambientales de forma significativa.
              </p>
            </div>
          </div>
        </div>

        {/* Columna derecha: formulario */}
        <div className="w-full lg:w-5/12 flex flex-col justify-center p-space-lg lg:p-space-xl bg-surface-container-lowest text-on-surface">
          <div className="w-full max-w-md mx-auto flex flex-col">
            <div className="flex items-center justify-between mb-space-lg">
              <div className="flex flex-col">
                <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
                  Portal Legal Corporativo
                </span>
                <h2 className="font-headline-md text-headline-md text-primary font-bold">
                  {mode === "login" ? "Bienvenido" : "Crear Cuenta Corporativa"}
                </h2>
              </div>
              <div className="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center text-secondary">
                <span className="material-symbols-outlined">gavel</span>
              </div>
            </div>

            <div className="w-full bg-surface-container p-1 rounded-lg flex items-center mb-space-lg shadow-inner">
              <button
                type="button"
                onClick={() => setMode("login")}
                className={`flex-1 py-2 px-3 rounded-md font-label-md text-label-md transition-all duration-200 ${
                  mode === "login"
                    ? "bg-surface-container-lowest text-primary shadow-sm font-semibold"
                    : "text-on-surface-variant hover:text-primary"
                }`}
              >
                Iniciar Sesión
              </button>
              <button
                type="button"
                onClick={() => setMode("register")}
                className={`flex-1 py-2 px-3 rounded-md font-label-md text-label-md transition-all duration-200 ${
                  mode === "register"
                    ? "bg-surface-container-lowest text-primary shadow-sm font-semibold"
                    : "text-on-surface-variant hover:text-primary"
                }`}
              >
                Crear Cuenta
              </button>
            </div>

            <form
              className="space-y-space-md"
              onSubmit={mode === "login" ? handleLogin : handleRegister}
            >
              {mode === "register" && (
                <div className="space-y-1">
                  <Label>Empresa o Razón Social</Label>
                  <Input
                    placeholder="Ej. Celsia Energía S.A. E.S.P."
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    required
                  />
                  {slugPreview && (
                    <p className="font-label-sm text-label-sm text-outline">
                      Identificador de organización: <span className="text-secondary font-semibold">{slugPreview}</span>
                    </p>
                  )}
                </div>
              )}

              <div className="space-y-1">
                <Label>Correo Electrónico Corporativo</Label>
                <Input
                  type="email"
                  placeholder="cumplimiento@empresa.com.co"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-1">
                <Label>Contraseña</Label>
                <Input
                  type="password"
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={8}
                  required
                />
              </div>

              <ErrorBanner message={error} />

              <Button type="submit" disabled={loading} className="w-full mt-space-sm">
                <span>
                  {loading
                    ? "Procesando..."
                    : mode === "login"
                      ? "Ingresar a Ecolex"
                      : "Registrar Organización"}
                </span>
                <span className="material-symbols-outlined text-body-md">arrow_forward</span>
              </Button>
            </form>

            <div className="mt-space-xl pt-space-md border-t border-surface-variant text-center">
              <p className="font-label-sm text-label-sm text-outline">
                Cumplimiento de la <span className="text-secondary font-semibold">Ley 1581 de 2012</span> (Protección de Datos)
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

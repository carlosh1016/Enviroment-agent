"use client";

import Link from "next/link";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="min-h-screen bg-surface flex items-center justify-center p-space-md">
      <div className="max-w-md text-center flex flex-col items-center gap-space-md">
        <div className="w-14 h-14 rounded-2xl bg-error-container flex items-center justify-center text-error">
          <span className="material-symbols-outlined text-[28px]">error</span>
        </div>
        <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">
          Algo salió mal
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Ocurrió un error inesperado. Puedes intentar de nuevo o volver al dashboard.
        </p>
        <div className="flex items-center gap-space-sm">
          <button
            type="button"
            onClick={reset}
            className="px-space-md py-2.5 rounded-xl border border-outline-variant text-on-surface font-label-lg text-label-lg hover:bg-surface-container-low transition-all"
          >
            Reintentar
          </button>
          <Link
            href="/dashboard"
            className="inline-flex items-center px-space-md py-2.5 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary-container transition-all"
          >
            Volver al dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}

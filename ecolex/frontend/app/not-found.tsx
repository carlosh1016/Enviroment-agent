import Link from "next/link";

export default function NotFound() {
  return (
    <main className="min-h-screen bg-surface flex items-center justify-center p-space-md">
      <div className="max-w-md text-center flex flex-col items-center gap-space-md">
        <div className="w-14 h-14 rounded-2xl bg-surface-container-low flex items-center justify-center text-secondary">
          <span className="material-symbols-outlined text-[28px]">search_off</span>
        </div>
        <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">
          Página no encontrada
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          La página que buscas no existe o fue movida. Vuelve al inicio para seguir consultando
          normativa ambiental.
        </p>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-space-xs px-space-md py-2.5 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary-container transition-all"
        >
          Volver al dashboard
        </Link>
      </div>
    </main>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { EcolexMark } from "@/components/ecolex/logo";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/documents", label: "Documentos", icon: "folder_open" },
  { href: "/chat", label: "Chat Asistente", icon: "chat" },
  { href: "/users", label: "Usuarios & Equipo", icon: "group", adminOnly: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const clearSession = useAuthStore((state) => state.clearSession);

  const tenantName = user?.tenant_name ?? "Organización";
  const visibleItems = NAV_ITEMS.filter((item) => !item.adminOnly || user?.role === "admin");

  async function handleLogout() {
    try {
      await api.post("/auth/logout");
    } catch (err) {
      // La sesion local se cierra igual aunque el servidor no responda.
      console.error("No se pudo cerrar la sesión en el servidor", err);
    } finally {
      clearSession();
      router.push("/login");
    }
  }

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-primary-container text-on-primary z-50 flex flex-col justify-between p-space-lg shadow-[0_4px_24px_rgba(1,45,29,0.18)]">
      <div className="flex flex-col gap-space-xl">
        <div className="flex items-center gap-space-sm pb-space-md">
          <EcolexMark className="h-8 w-8 object-contain" />
          <div className="flex flex-col">
            <span className="font-title-md text-title-md text-on-primary tracking-tight">Ecolex</span>
            <span className="font-label-sm text-label-sm text-on-primary-container uppercase tracking-wider">
              IA Jurídica
            </span>
          </div>
        </div>
        <nav className="flex flex-col gap-space-xs">
          {visibleItems.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-space-sm px-space-md py-space-sm rounded-xl transition-all font-label-lg text-label-lg",
                  active
                    ? "bg-secondary text-on-secondary shadow-sm"
                    : "text-primary-fixed hover:bg-tertiary-container hover:text-on-primary"
                )}
              >
                <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex flex-col gap-space-sm">
        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-space-sm px-space-md py-space-sm rounded-xl font-label-lg text-label-lg text-primary-fixed hover:bg-error-container hover:text-on-error-container transition-all"
        >
          <span className="material-symbols-outlined text-[20px]">logout</span>
          <span>Cerrar sesión</span>
        </button>
        <div className="flex flex-col gap-space-sm p-space-md bg-tertiary-container rounded-xl">
          <div className="flex items-center gap-space-xs">
            <span className="material-symbols-outlined text-[18px] text-secondary-fixed">corporate_fare</span>
            <span className="font-label-md text-label-md text-on-primary font-bold truncate">{tenantName}</span>
          </div>
          <div className="flex items-center gap-space-xs pt-space-xs">
            <span className="w-2 h-2 rounded-full bg-secondary-fixed-dim animate-pulse" />
            <span className="font-label-sm text-label-sm text-primary-fixed-dim">
              Normativa ambiental • Colombia
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}

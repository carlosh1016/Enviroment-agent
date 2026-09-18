"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { getErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/utils";
import { ErrorBanner } from "@/components/ui/error-banner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import type { ApiEnvelope, ManagedUser, PaginatedResponse, UserRoleValue } from "@/lib/types";

const ROLE_LABEL: Record<UserRoleValue, string> = {
  admin: "Administrador",
  analyst: "Analista Jurídico",
  viewer: "Visualizador / Auditor",
};

const ASSIGNABLE_ROLES: UserRoleValue[] = ["analyst", "viewer"];

export default function UsersPage() {
  const router = useRouter();
  const currentUser = useAuthStore((state) => state.user);
  const isAdmin = currentUser?.role === "admin";

  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteSubmitting, setInviteSubmitting] = useState(false);
  const [rowBusyId, setRowBusyId] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const loadUsers = useCallback(async () => {
    try {
      const res = await api.get<ApiEnvelope<PaginatedResponse<ManagedUser>>>("/api/v1/users/", {
        params: { page_size: 50 },
      });
      setUsers(res.data.data.items);
    } catch (err) {
      setPageError(getErrorMessage(err, "No se pudo cargar la lista de usuarios."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Guard de rol: esta pantalla es solo para administradores del tenant.
    if (currentUser && !isAdmin) {
      router.replace("/dashboard");
      return;
    }
    if (isAdmin) {
      loadUsers();
    }
  }, [currentUser, isAdmin, router, loadUsers]);

  async function handleInvite(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setInviteError(null);
    setInviteSubmitting(true);

    const form = e.currentTarget;
    const email = (form.elements.namedItem("inviteEmail") as HTMLInputElement).value;
    const password = (form.elements.namedItem("invitePassword") as HTMLInputElement).value;
    const role = (form.elements.namedItem("inviteRole") as HTMLSelectElement).value as UserRoleValue;

    try {
      await api.post("/api/v1/users/", { email, password, role });
      setInviteOpen(false);
      form.reset();
      await loadUsers();
    } catch (err) {
      setInviteError(getErrorMessage(err, "No se pudo crear el usuario."));
    } finally {
      setInviteSubmitting(false);
    }
  }

  async function handleRoleChange(userId: string, role: UserRoleValue) {
    setRowBusyId(userId);
    setPageError(null);
    try {
      await api.patch(`/api/v1/users/${userId}`, { role });
      await loadUsers();
    } catch (err) {
      setPageError(getErrorMessage(err, "No se pudo cambiar el rol del usuario."));
    } finally {
      setRowBusyId(null);
    }
  }

  async function handleDeactivate(userId: string) {
    if (!confirm("¿Desactivar el acceso de este usuario?")) return;
    setRowBusyId(userId);
    setPageError(null);
    try {
      await api.delete(`/api/v1/users/${userId}`);
      await loadUsers();
    } catch (err) {
      setPageError(getErrorMessage(err, "No se pudo desactivar al usuario."));
    } finally {
      setRowBusyId(null);
    }
  }

  async function handleReactivate(userId: string) {
    setRowBusyId(userId);
    setPageError(null);
    try {
      await api.patch(`/api/v1/users/${userId}`, { is_active: true });
      await loadUsers();
    } catch (err) {
      setPageError(getErrorMessage(err, "No se pudo reactivar al usuario."));
    } finally {
      setRowBusyId(null);
    }
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <div className="flex flex-col w-full gap-space-lg">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col">
          <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">
            Gestión de Usuarios
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant mt-1 max-w-2xl">
            Administra los accesos de tu equipo dentro de la organización.
          </p>
        </div>
        <Button type="button" onClick={() => setInviteOpen(true)}>
          <span className="material-symbols-outlined text-[18px]">person_add</span>
          <span>Invitar usuario</span>
        </Button>
      </div>

      <ErrorBanner message={pageError} />

      <div className="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden flex flex-col">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Usuario</TableHead>
              <TableHead>Rol</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Creado</TableHead>
              <TableHead className="text-right">Acciones</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!loading && !pageError && users.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-on-surface-variant py-space-xl">
                  Aún no hay otros usuarios en esta organización.
                </TableCell>
              </TableRow>
            )}
            {users.map((u) => {
              const isSelf = u.id === currentUser?.id;
              const busy = rowBusyId === u.id;
              return (
                <TableRow key={u.id}>
                  <TableCell>
                    <span className="font-title-md text-title-md text-primary font-bold">{u.email}</span>
                    {isSelf && (
                      <span className="ml-2 font-label-sm text-label-sm text-outline">(tú)</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {u.role === "admin" || isSelf ? (
                      <span className="inline-flex items-center px-space-sm py-1 rounded-md font-label-sm text-label-sm bg-surface-container-high text-on-surface font-semibold">
                        {ROLE_LABEL[u.role]}
                      </span>
                    ) : (
                      <select
                        value={u.role}
                        disabled={busy}
                        onChange={(e) => handleRoleChange(u.id, e.target.value as UserRoleValue)}
                        className="bg-surface-container-low text-on-surface font-label-sm text-label-sm rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-secondary disabled:opacity-50"
                      >
                        {ASSIGNABLE_ROLES.map((role) => (
                          <option key={role} value={role}>
                            {ROLE_LABEL[role]}
                          </option>
                        ))}
                      </select>
                    )}
                  </TableCell>
                  <TableCell>
                    <span
                      className={`inline-flex items-center gap-1.5 px-space-sm py-0.5 rounded-full font-label-sm text-label-sm font-medium ${
                        u.is_active ? "bg-emerald-50 text-emerald-800" : "bg-red-100 text-red-900"
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${u.is_active ? "bg-secondary" : "bg-error"}`} />
                      {u.is_active ? "Activo" : "Inactivo"}
                    </span>
                  </TableCell>
                  <TableCell className="text-on-surface-variant font-body-sm text-body-sm">
                    {formatDate(u.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    {!isSelf && !u.is_active && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleReactivate(u.id)}
                        className="px-2 py-1 rounded-lg bg-surface-container-high text-primary hover:bg-surface-container-highest font-label-sm text-label-sm font-medium transition-colors disabled:opacity-50"
                        title="Reactivar usuario"
                      >
                        Reactivar
                      </button>
                    )}
                    {!isSelf && u.is_active && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleDeactivate(u.id)}
                        className="p-1.5 rounded-lg text-error hover:bg-error-container hover:text-on-error-container transition-colors disabled:opacity-50"
                        title="Desactivar usuario"
                      >
                        <span className="material-symbols-outlined text-[18px]">person_remove</span>
                      </button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invitar Miembro</DialogTitle>
            <DialogDescription>
              Crea un usuario con una contraseña temporal. No se pueden crear administradores desde
              aquí.
            </DialogDescription>
          </DialogHeader>
          <form className="flex flex-col gap-space-md" onSubmit={handleInvite}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="inviteEmail">Correo corporativo</Label>
              <Input id="inviteEmail" name="inviteEmail" type="email" placeholder="ejemplo@empresa.com" required />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="invitePassword">Contraseña temporal</Label>
              <Input
                id="invitePassword"
                name="invitePassword"
                type="password"
                placeholder="Mínimo 8 caracteres"
                minLength={8}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="inviteRole">Rol</Label>
              <select
                id="inviteRole"
                name="inviteRole"
                defaultValue="analyst"
                className="w-full px-3 py-2.5 rounded-lg bg-surface-container-low text-on-surface font-body-md text-body-md focus:outline-none focus:ring-1 focus:ring-secondary"
              >
                {ASSIGNABLE_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABEL[role]}
                  </option>
                ))}
              </select>
            </div>

            <ErrorBanner message={inviteError} />

            <div className="flex items-center gap-space-xs pt-space-xs">
              <DialogClose asChild>
                <Button type="button" variant="outline" className="flex-1">
                  Cancelar
                </Button>
              </DialogClose>
              <Button type="submit" disabled={inviteSubmitting} className="flex-1">
                {inviteSubmitting ? "Enviando..." : "Crear usuario"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

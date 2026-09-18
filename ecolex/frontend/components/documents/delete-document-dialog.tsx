"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";

interface DeleteDocumentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filename: string;
  onConfirm: () => void;
  loading?: boolean;
  error?: string | null;
}

export function DeleteDocumentDialog({
  open,
  onOpenChange,
  filename,
  onConfirm,
  loading,
  error,
}: DeleteDocumentDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Eliminar documento</DialogTitle>
          <DialogDescription>
            ¿Seguro que quieres eliminar <span className="font-semibold text-on-surface">{filename}</span>?
            Esta acción no se puede revertir y también se eliminarán sus fragmentos indexados.
          </DialogDescription>
        </DialogHeader>
        <ErrorBanner message={error ?? null} className="mb-space-md" />
        <div className="flex items-center justify-end gap-space-sm">
          <DialogClose asChild>
            <Button variant="outline" type="button">
              Cancelar
            </Button>
          </DialogClose>
          <Button variant="destructive" type="button" disabled={loading} onClick={onConfirm}>
            {loading ? "Eliminando..." : "Eliminar"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

"use client";

import { useCallback, useRef, useState } from "react";
import { validateFile } from "@/lib/documents";

interface UploadDropzoneProps {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}

export function UploadDropzone({ onFiles, disabled }: UploadDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;
      const files = Array.from(fileList);
      for (const file of files) {
        const err = validateFile(file);
        if (err) {
          setError(`${file.name}: ${err}`);
          return;
        }
      }
      setError(null);
      onFiles(files);
    },
    [onFiles]
  );

  return (
    <div
      className={`relative overflow-hidden rounded-xl bg-surface-container-low p-space-lg shadow-sm transition-colors ${
        dragging ? "ring-2 ring-secondary" : ""
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!disabled) handleFiles(e.dataTransfer.files);
      }}
    >
      <div className="relative bg-surface-container-lowest/80 rounded-xl p-space-lg flex flex-col items-center justify-center text-center shadow-sm">
        <div className="w-14 h-14 rounded-2xl bg-surface-container-low flex items-center justify-center text-secondary shadow-sm mb-space-sm">
          <span className="material-symbols-outlined text-[30px]">cloud_upload</span>
        </div>
        <h3 className="font-headline-sm text-headline-sm text-primary mb-1">
          Arrastre aquí archivos PDF, DOCX o TXT
        </h3>
        <p className="font-body-md text-body-md text-on-surface-variant max-w-xl mb-space-md">
          Tamaño máximo 10MB por archivo. Se procesarán en segundo plano y aparecerán como
          &quot;Procesando&quot; en la tabla hasta quedar listos.
        </p>
        <label className="cursor-pointer inline-flex items-center gap-space-xs px-space-md py-space-sm bg-secondary text-on-secondary rounded-xl font-label-lg text-label-lg shadow-sm hover:bg-on-secondary-container transition-all">
          <span className="material-symbols-outlined text-[18px]">add_circle</span>
          <span>O seleccionar archivos desde su equipo</span>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt"
            className="hidden"
            disabled={disabled}
            onChange={(e) => {
              handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        {error && (
          <p className="mt-space-sm font-body-sm text-body-sm text-error bg-error-container/40 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

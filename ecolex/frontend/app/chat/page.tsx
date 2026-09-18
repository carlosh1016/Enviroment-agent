export default function ChatIndexPage() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-space-sm text-center p-space-xl">
      <div className="w-14 h-14 rounded-2xl bg-surface-container-low flex items-center justify-center text-secondary">
        <span className="material-symbols-outlined text-[28px]">gavel</span>
      </div>
      <h2 className="font-headline-sm text-headline-sm text-primary">
        Selecciona o crea una consulta jurídica
      </h2>
      <p className="font-body-md text-body-md text-on-surface-variant max-w-md">
        Elige una conversación del panel izquierdo o crea una nueva para empezar a consultar al
        agente sobre normativa ambiental colombiana.
      </p>
    </div>
  );
}

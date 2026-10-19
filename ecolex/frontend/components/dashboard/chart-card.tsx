/** Envoltorio visual comun para las tarjetas de grafica del dashboard: mismo estilo de
 * tarjeta que las metricas numericas de arriba (bg-surface-container-lowest, sombra, radio). */
export function ChartCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-surface-container-lowest p-space-lg rounded-xl shadow-sm flex flex-col gap-space-sm">
      <div className="flex items-center gap-space-xs">
        <span className="material-symbols-outlined text-secondary text-[20px]">{icon}</span>
        <h3 className="font-label-lg text-label-lg text-on-surface-variant uppercase tracking-wider">
          {title}
        </h3>
      </div>
      {children}
    </div>
  );
}

/** Mensaje consistente cuando una grafica no tiene datos suficientes para dibujarse. */
export function ChartEmptyState({ message }: { message: string }) {
  return (
    <div className="h-[220px] flex items-center justify-center">
      <p className="font-body-sm text-body-sm text-on-surface-variant text-center max-w-xs">{message}</p>
    </div>
  );
}

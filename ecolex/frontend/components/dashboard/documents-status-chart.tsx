"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { ChartCard, ChartEmptyState } from "./chart-card";

// Mismos colores semanticos que components/ui/badge.tsx (ready=verde, processing=amarillo,
// error=rojo), para que la grafica y las badges de la tabla de documentos se lean igual.
const STATUS_COLORS: Record<string, string> = {
  ready: "#10b981",
  processing: "#f59e0b",
  error: "#ba1a1a",
};

const STATUS_LABELS: Record<string, string> = {
  ready: "Listos",
  processing: "Procesando",
  error: "Con error",
};

export function DocumentsStatusChart({ data }: { data: Record<string, number> }) {
  const chartData = Object.entries(data)
    .filter(([, value]) => value > 0)
    .map(([status, value]) => ({ status, value, label: STATUS_LABELS[status] ?? status }));

  const total = chartData.reduce((sum, item) => sum + item.value, 0);

  return (
    <ChartCard title="Documentos por estado" icon="donut_small">
      {total === 0 ? (
        <ChartEmptyState message="Aún no has subido documentos propios." />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie data={chartData} dataKey="value" nameKey="label" innerRadius={55} outerRadius={85} paddingAngle={2}>
              {chartData.map((entry) => (
                <Cell key={entry.status} fill={STATUS_COLORS[entry.status] ?? "#717973"} />
              ))}
            </Pie>
            <Tooltip formatter={(value, _name, item) => [value, item.payload.label]} />
          </PieChart>
        </ResponsiveContainer>
      )}
      <div className="flex flex-wrap gap-space-md justify-center">
        {chartData.map((entry) => (
          <div key={entry.status} className="flex items-center gap-1.5">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: STATUS_COLORS[entry.status] ?? "#717973" }}
            />
            <span className="font-body-sm text-body-sm text-on-surface-variant">
              {entry.label} ({entry.value})
            </span>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}

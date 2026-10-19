"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard, ChartEmptyState } from "./chart-card";

const TYPE_LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "DOCX",
  txt: "TXT",
  mhtml: "MHTML",
  html: "HTML",
  xlsx: "XLSX",
  csv: "CSV",
};

export function DocumentsTypeChart({ data }: { data: Record<string, number> }) {
  const chartData = Object.entries(data)
    .filter(([, value]) => value > 0)
    .map(([type, value]) => ({ type: TYPE_LABELS[type] ?? type.toUpperCase(), value }))
    .sort((a, b) => b.value - a.value);

  return (
    <ChartCard title="Documentos por tipo" icon="bar_chart">
      {chartData.length === 0 ? (
        <ChartEmptyState message="Aún no has subido documentos propios." />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} margin={{ left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e2e1" />
            <XAxis dataKey="type" tick={{ fontSize: 12, fill: "#414844" }} axisLine={{ stroke: "#c1c8c2" }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#414844" }} axisLine={{ stroke: "#c1c8c2" }} />
            <Tooltip />
            <Bar dataKey="value" name="Documentos" fill="#006c48" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

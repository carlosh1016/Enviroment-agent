"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CitedDocument } from "@/lib/types";
import { ChartCard, ChartEmptyState } from "./chart-card";

const MAX_LABEL_CHARS = 28;

function _truncate(name: string): string {
  return name.length > MAX_LABEL_CHARS ? `${name.slice(0, MAX_LABEL_CHARS - 1)}…` : name;
}

export function TopCitedChart({ data }: { data: CitedDocument[] }) {
  const chartData = data.map((doc) => ({ ...doc, label: _truncate(doc.document_name) }));

  return (
    <ChartCard title="Normas más citadas en el chat" icon="gavel">
      {chartData.length === 0 ? (
        <ChartEmptyState message="Aún no hay respuestas del asistente con fuentes citadas." />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e2e1" />
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: "#414844" }} />
            <YAxis
              type="category"
              dataKey="label"
              width={160}
              tick={{ fontSize: 11, fill: "#414844" }}
              axisLine={{ stroke: "#c1c8c2" }}
            />
            <Tooltip
              formatter={(value) => [value, "Citas"]}
              labelFormatter={(_label, payload) => payload?.[0]?.payload.document_name ?? ""}
            />
            <Bar dataKey="citations" name="Citas" fill="#002d1e" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

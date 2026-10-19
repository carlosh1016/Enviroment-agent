"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DayActivity } from "@/lib/types";
import { ChartCard, ChartEmptyState } from "./chart-card";

function _shortDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString("es-CO", { day: "2-digit", month: "short" });
}

export function ActivityChart({ data }: { data: DayActivity[] }) {
  const hasActivity = data.some((day) => day.conversations > 0 || day.messages > 0);
  const chartData = data.map((day) => ({ ...day, label: _shortDate(day.date) }));

  return (
    <ChartCard title="Actividad (últimos 14 días)" icon="show_chart">
      {!hasActivity ? (
        <ChartEmptyState message="Aún no hay conversaciones en los últimos 14 días." />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e2e1" />
            <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#414844" }} axisLine={{ stroke: "#c1c8c2" }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#414844" }} axisLine={{ stroke: "#c1c8c2" }} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="conversations"
              name="Conversaciones"
              stroke="#012d1d"
              strokeWidth={2}
              dot={false}
            />
            <Line type="monotone" dataKey="messages" name="Mensajes" stroke="#52B788" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

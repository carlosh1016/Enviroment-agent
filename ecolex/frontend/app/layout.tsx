import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ecolex — Asistente Legal Ambiental",
  description: "Plataforma SaaS de consulta de normativa ambiental colombiana con agente RAG.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className="antialiased">{children}</body>
    </html>
  );
}

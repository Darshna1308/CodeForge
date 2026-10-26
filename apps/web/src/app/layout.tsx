import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { Nav } from "@/components/Nav";
import { AuthProvider } from "@/lib/auth";

import "./globals.css";

export const metadata: Metadata = {
  title: "CodeForge — distributed online judge",
  description: "Asynchronous, sandboxed code execution and judging: Redis Streams workers, Docker isolation, live SSE status.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="noise min-h-screen">
        <div className="bg-grid pointer-events-none fixed inset-0 -z-10" />
        <AuthProvider>
          <Nav />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}

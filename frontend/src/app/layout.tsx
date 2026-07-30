import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { Providers } from "@/components/providers";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Dharma AI — Autonomous Contract Review & Negotiation",
    template: "%s · Dharma AI",
  },
  description:
    "A multi-agent contract review and negotiation platform. Nine Lyzr agents classify " +
    "clauses, score risk against your playbook, draft redlines, and negotiate — with " +
    "guardrails and a human approval gate on every change.",
  keywords: [
    "contract review",
    "AI legal",
    "contract negotiation",
    "clause analysis",
    "legal tech",
    "multi-agent AI",
  ],
  authors: [{ name: "Dharma AI" }],
  openGraph: {
    title: "Dharma AI — Autonomous Contract Review & Negotiation",
    description:
      "Nine Lyzr agents review, redline and negotiate your contracts. Every AI decision " +
      "auditable, every redline human-approved.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#07090c",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} dark`}>
      <body className="min-h-dvh bg-base-950 font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

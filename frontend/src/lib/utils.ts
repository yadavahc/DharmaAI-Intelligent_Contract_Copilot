import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

import type { RiskLevel } from "@/lib/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/* ──────────────────────────────────────────────────────────────────────────
 * Risk presentation
 *
 * Centralised so a risk level always looks the same everywhere. Returning class
 * strings (not raw colours) keeps the token indirection intact.
 * ────────────────────────────────────────────────────────────────────────── */

export const RISK_LEVELS: RiskLevel[] = ["Low", "Medium", "High", "Critical"];

export function riskClasses(level: string | undefined) {
  switch (level) {
    case "Critical":
      return {
        text: "text-risk-critical",
        bg: "bg-risk-critical/12",
        border: "border-risk-critical/30",
        ring: "ring-risk-critical/25",
        dot: "bg-risk-critical",
        raw: "hsl(var(--risk-critical))",
      };
    case "High":
      return {
        text: "text-risk-high",
        bg: "bg-risk-high/12",
        border: "border-risk-high/30",
        ring: "ring-risk-high/25",
        dot: "bg-risk-high",
        raw: "hsl(var(--risk-high))",
      };
    case "Medium":
      return {
        text: "text-risk-medium",
        bg: "bg-risk-medium/12",
        border: "border-risk-medium/30",
        ring: "ring-risk-medium/25",
        dot: "bg-risk-medium",
        raw: "hsl(var(--risk-medium))",
      };
    default:
      return {
        text: "text-risk-low",
        bg: "bg-risk-low/12",
        border: "border-risk-low/30",
        ring: "ring-risk-low/25",
        dot: "bg-risk-low",
        raw: "hsl(var(--risk-low))",
      };
  }
}

/** Chart-ready colours, resolved from the same tokens. */
export const RISK_COLORS: Record<RiskLevel, string> = {
  Low: "hsl(var(--risk-low))",
  Medium: "hsl(var(--risk-medium))",
  High: "hsl(var(--risk-high))",
  Critical: "hsl(var(--risk-critical))",
};

/** Categorical palette for non-risk charts (category mix, negotiation status). */
export const CHART_PALETTE = [
  "hsl(160 84% 45%)",
  "hsl(200 85% 58%)",
  "hsl(265 72% 66%)",
  "hsl(38 92% 58%)",
  "hsl(320 70% 62%)",
  "hsl(180 70% 48%)",
  "hsl(18 90% 60%)",
  "hsl(230 75% 66%)",
  "hsl(95 60% 50%)",
  "hsl(352 75% 62%)",
];

export function severityClasses(severity: string | undefined) {
  switch (severity) {
    case "critical":
      return "text-risk-critical bg-risk-critical/12 border-risk-critical/30";
    case "high":
      return "text-risk-high bg-risk-high/12 border-risk-high/30";
    case "medium":
      return "text-risk-medium bg-risk-medium/12 border-risk-medium/30";
    case "low":
      return "text-silver-300 bg-base-700/50 border-silver-50/10";
    default:
      return "text-risk-low bg-risk-low/12 border-risk-low/30";
  }
}

/* ──────────────────────────────────────────────────────────────────────────
 * Formatting
 * ────────────────────────────────────────────────────────────────────────── */

export function formatPct(value: number | undefined | null, digits = 0) {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  // Accept either 0–1 or 0–100 and normalise.
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(digits)}%`;
}

export function formatScore(value: number | undefined | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelative(iso: string | null | undefined) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return "just now";
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [3600, "minute"],
    [86400, "hour"],
    [604800, "day"],
    [2629800, "week"],
    [31557600, "month"],
  ];
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  let previous = 1;
  for (const [limit, unit] of units) {
    if (seconds < limit) {
      return formatter.format(-Math.round(seconds / previous), unit);
    }
    previous = limit;
  }
  return formatter.format(-Math.round(seconds / 31557600), "year");
}

export function truncate(text: string | undefined | null, max = 120) {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}

export function titleCase(text: string | undefined | null) {
  if (!text) return "";
  return text
    .replace(/[_.]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

export function initials(name: string | undefined | null) {
  if (!name) return "?";
  const parts = name.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?").concat(parts[1]?.[0] ?? "").toUpperCase();
}

/** Actor-type styling for the audit log. */
export function actorClasses(actorType: string | undefined) {
  switch (actorType) {
    case "ai_agent":
      return { text: "text-accent-soft", bg: "bg-accent/10", border: "border-accent/25", label: "AI Agent" };
    case "human":
      return { text: "text-[hsl(200_85%_65%)]", bg: "bg-[hsl(200_85%_58%)]/10", border: "border-[hsl(200_85%_58%)]/25", label: "Human" };
    default:
      return { text: "text-silver-300", bg: "bg-base-700/50", border: "border-silver-50/10", label: "System" };
  }
}

export const ROLE_LABELS: Record<string, string> = {
  ADMIN: "Admin",
  REVIEWER: "Reviewer",
  BUSINESS_USER: "Business User",
};

/** Roles permitted to act on the approval gate — mirrors the backend rule. */
export function canApprove(role: string | undefined | null) {
  return role === "REVIEWER" || role === "ADMIN";
}

export function canManagePlaybook(role: string | undefined | null) {
  return role === "ADMIN";
}

export function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

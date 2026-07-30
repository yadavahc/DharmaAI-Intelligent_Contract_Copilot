"use client";

import {
  ChevronDown,
  CircleCheck,
  Eraser,
  Ban,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { Collapse } from "@/components/ui/motion";
import { Badge, Card } from "@/components/ui/primitives";
import type { GuardrailVerdict } from "@/lib/types";
import { cn, severityClasses, titleCase } from "@/lib/utils";

const ACTION_META: Record<
  string,
  { icon: LucideIcon; label: string; className: string }
> = {
  allow: { icon: CircleCheck, label: "Allowed", className: "text-risk-low" },
  flag: { icon: ShieldAlert, label: "Flagged", className: "text-risk-medium" },
  sanitize: { icon: Eraser, label: "Neutralised", className: "text-risk-high" },
  block: { icon: Ban, label: "Blocked", className: "text-risk-critical" },
  require_approval: {
    icon: UserCheck,
    label: "Approval required",
    className: "text-risk-high",
  },
};

/**
 * Renders a guardrail verdict exactly as the backend produced it.
 *
 * Deliberately shows the matched evidence: a guardrail that only says "blocked"
 * is impossible to trust or debug, so the rule name, severity and matched excerpt
 * are all surfaced.
 */
export function GuardrailVerdictCard({
  verdict,
  compact = false,
  defaultOpen,
}: {
  verdict: GuardrailVerdict;
  compact?: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen ?? verdict.triggered);
  const meta = ACTION_META[verdict.action] ?? ACTION_META.allow;
  const Icon = verdict.triggered ? meta.icon : ShieldCheck;

  return (
    <Card
      flush
      className={cn(
        "overflow-hidden",
        verdict.triggered
          ? verdict.severity === "critical"
            ? "border-risk-critical/25"
            : verdict.severity === "high"
              ? "border-risk-high/25"
              : "border-risk-medium/25"
          : "border-risk-low/20",
      )}
      data-testid={`guardrail-${verdict.guardrail}`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-base-800/40"
        aria-expanded={open}
      >
        <Icon
          className={cn(
            "mt-0.5 size-4 shrink-0",
            verdict.triggered ? meta.className : "text-risk-low",
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-semibold text-silver-100">
              {titleCase(verdict.guardrail)}
            </p>
            <Badge
              variant={verdict.triggered ? "high" : "low"}
              size="sm"
              className={cn(verdict.triggered && severityClasses(verdict.severity))}
            >
              {verdict.triggered ? `${verdict.severity} · ${meta.label}` : "passed"}
            </Badge>
            {verdict.findings.length > 0 && (
              <span className="numeric text-2xs text-silver-500">
                {verdict.findings.length} finding
                {verdict.findings.length === 1 ? "" : "s"}
              </span>
            )}
          </div>
          {!compact || verdict.triggered ? (
            <p className="mt-1.5 text-2xs leading-relaxed text-silver-400">{verdict.summary}</p>
          ) : null}
        </div>
        <ChevronDown
          className={cn(
            "mt-0.5 size-3.5 shrink-0 text-silver-500 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>

      <Collapse open={open}>
        <div className="border-t border-silver-50/[0.06] px-4 py-3">
          {compact && <p className="mb-3 text-2xs leading-relaxed text-silver-400">{verdict.summary}</p>}

          {verdict.findings.length === 0 ? (
            <p className="text-2xs text-silver-500">
              No findings — nothing matched any rule in this guardrail.
            </p>
          ) : (
            <ul className="space-y-2">
              {verdict.findings.map((finding, i) => (
                <li
                  key={`${finding.rule}-${i}`}
                  className="rounded-md border border-silver-50/[0.06] bg-base-900/50 p-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="font-mono text-[0.625rem] font-semibold text-accent-soft">
                      {finding.rule}
                    </code>
                    <Badge
                      size="sm"
                      className={cn("border", severityClasses(finding.severity))}
                    >
                      {finding.severity}
                    </Badge>
                    {finding.position >= 0 && (
                      <span className="numeric text-[0.625rem] text-silver-600">
                        @{finding.position}
                      </span>
                    )}
                  </div>
                  <p className="mt-1.5 break-words font-mono text-2xs leading-relaxed text-silver-300">
                    {finding.excerpt}
                  </p>
                  {finding.note && (
                    <p className="mt-1.5 text-[0.625rem] leading-relaxed text-silver-500">
                      {finding.note}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}

          {Object.keys(verdict.details ?? {}).length > 0 && (
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-silver-50/[0.06] pt-3">
              {Object.entries(verdict.details).map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <dt className="text-[0.625rem] uppercase tracking-wider text-silver-600">
                    {titleCase(key)}
                  </dt>
                  <dd className="truncate font-mono text-2xs text-silver-300">
                    {Array.isArray(value)
                      ? value.length
                        ? value.join(", ")
                        : "none"
                      : typeof value === "object" && value !== null
                        ? JSON.stringify(value)
                        : String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </Collapse>
    </Card>
  );
}

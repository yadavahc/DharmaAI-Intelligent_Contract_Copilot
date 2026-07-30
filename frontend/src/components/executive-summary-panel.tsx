"use client";

import {
  CalendarClock,
  Download,
  FileSignature,
  Loader2,
  RefreshCw,
  Sparkles,
  Wallet,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { AnimatePresence, motion } from "@/components/ui/motion";
import { Badge, Button, Card, CardTitle, Skeleton } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { ExecutiveSummary } from "@/lib/types";
import { cn, formatPct } from "@/lib/utils";

/**
 * Feature 5 — Executive AI Summary.
 *
 * One click produces a one-page plain-English brief, shown in a modal and
 * exportable to PDF. Generated server-side by the Executive Briefing agent and
 * cached on the contract, so reopening is instant; `refresh` forces a regenerate.
 */
export function ExecutiveSummaryPanel({
  contractId,
  contractTitle,
}: {
  contractId: string;
  contractTitle: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [summary, setSummary] = React.useState<ExecutiveSummary | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [exporting, setExporting] = React.useState(false);

  const generate = async (refresh = false) => {
    setLoading(true);
    setOpen(true);
    try {
      const result = await api.executiveSummary(contractId, refresh);
      setSummary(result);
      if (refresh) toast.success("Brief regenerated");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : String(err);
      toast.error("Could not generate the brief", { description: message });
      setOpen(false);
    } finally {
      setLoading(false);
    }
  };

  const exportPdf = async () => {
    if (!summary) return;
    setExporting(true);
    try {
      // Imported lazily: jsPDF is ~350 KB and only needed if someone exports.
      const { jsPDF } = await import("jspdf");
      const doc = new jsPDF({ unit: "pt", format: "a4" });

      const MARGIN = 48;
      const WIDTH = doc.internal.pageSize.getWidth() - MARGIN * 2;
      const PAGE_HEIGHT = doc.internal.pageSize.getHeight();
      let y = MARGIN;

      const ensureRoom = (needed: number) => {
        if (y + needed > PAGE_HEIGHT - MARGIN) {
          doc.addPage();
          y = MARGIN;
        }
      };

      const write = (
        text: string,
        { size = 10, style = "normal", gap = 6, color = "#1f2937" as string } = {},
      ) => {
        doc.setFont("helvetica", style);
        doc.setFontSize(size);
        doc.setTextColor(color);
        const lines = doc.splitTextToSize(text, WIDTH) as string[];
        ensureRoom(lines.length * (size + 3));
        doc.text(lines, MARGIN, y);
        y += lines.length * (size + 3) + gap;
      };

      const heading = (text: string) => {
        ensureRoom(28);
        y += 6;
        write(text.toUpperCase(), { size: 9, style: "bold", gap: 4, color: "#0f766e" });
        doc.setDrawColor("#d1d5db");
        doc.line(MARGIN, y - 4, MARGIN + WIDTH, y - 4);
        y += 4;
      };

      const bullets = (items: string[]) => {
        if (!items.length) {
          write("None identified.", { size: 10, color: "#6b7280" });
          return;
        }
        items.forEach((item) => write(`•  ${item}`, { size: 10, gap: 3 }));
      };

      // ── header ──
      write("DHARMA AI — EXECUTIVE BRIEF", { size: 8, style: "bold", gap: 3, color: "#6b7280" });
      write(contractTitle, { size: 17, style: "bold", gap: 4, color: "#111827" });
      write(
        `Generated ${new Date().toLocaleString()} · AI confidence ${formatPct(summary.confidence)}`,
        { size: 8, gap: 12, color: "#6b7280" },
      );

      write(summary.headline, { size: 11, style: "bold", gap: 12, color: "#111827" });

      heading("Recommendation");
      write(summary.overall_recommendation || "—", { size: 10, style: "bold" });

      heading("Financial exposure");
      write(summary.financial_exposure?.headline_figure ?? "Not quantified", {
        size: 13,
        style: "bold",
        gap: 3,
        color: "#b91c1c",
      });
      if (summary.financial_exposure?.notes) {
        write(summary.financial_exposure.notes, { size: 9, color: "#4b5563" });
      }

      heading("Key obligations");
      bullets(summary.key_obligations ?? []);

      heading("Dates & deadlines");
      bullets(summary.deadlines ?? []);

      heading("Renewal");
      write(summary.renewal_terms || "—", { size: 10 });

      heading("Top risks");
      if (!summary.top_risks?.length) {
        write("No high-risk clauses identified.", { size: 10, color: "#6b7280" });
      } else {
        summary.top_risks.forEach((r) => {
          write(`${r.clause} — ${r.risk}`, { size: 10, style: "bold", gap: 2 });
          write(r.why, { size: 9, gap: 6, color: "#4b5563" });
        });
      }

      heading("Recommended actions");
      bullets(summary.recommended_actions ?? []);

      y += 10;
      write(
        "This brief was produced by an AI agent and is a summary, not legal advice. " +
          "Every AI-proposed change is subject to human approval before it is finalised.",
        { size: 7.5, color: "#9ca3af" },
      );

      const safeName = contractTitle.replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-");
      doc.save(`dharma-executive-brief-${safeName || contractId}.pdf`);
      toast.success("PDF exported");
    } catch (err) {
      toast.error("PDF export failed", { description: String(err) });
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <Card
        hover
        className="flex h-full cursor-pointer flex-col justify-between border-accent/20 bg-accent/[0.04]"
        onClick={() => (summary ? setOpen(true) : generate(false))}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            summary ? setOpen(true) : generate(false);
          }
        }}
        data-testid="exec-summary-trigger"
      >
        <div>
          <div className="flex items-start justify-between">
            <p className="text-2xs uppercase tracking-wider text-accent-soft">Executive brief</p>
            <Sparkles className="size-3.5 shrink-0 text-accent" />
          </div>
          <p className="mt-2 text-sm font-semibold leading-snug text-silver-100">
            One-page plain-English summary
          </p>
        </div>
        <p className="mt-3 text-2xs text-silver-500">
          {summary ? "View brief →" : loading ? "Generating…" : "Generate →"}
        </p>
      </Card>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 bg-base-950/85 backdrop-blur-sm"
              onClick={() => setOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.97, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.97, y: 12 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="fixed inset-x-4 top-[4vh] z-50 mx-auto max-h-[92vh] max-w-3xl overflow-y-auto rounded-xl border border-silver-50/10 bg-base-900/95 shadow-glass-lg backdrop-blur-xl sm:inset-x-8"
              role="dialog"
              aria-modal="true"
              aria-label="Executive brief"
            >
              {/* ── modal header ── */}
              <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-silver-50/[0.07] bg-base-900/95 px-6 py-4 backdrop-blur">
                <div className="min-w-0">
                  <p className="eyebrow mb-1">Executive brief</p>
                  <h2 className="truncate text-lg font-semibold text-silver-50">{contractTitle}</h2>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => generate(true)}
                    disabled={loading}
                    aria-label="Regenerate"
                  >
                    <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={exportPdf}
                    disabled={!summary || exporting}
                    loading={exporting}
                    data-testid="export-pdf"
                  >
                    <Download className="size-3.5" /> PDF
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setOpen(false)}
                    aria-label="Close"
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              </div>

              {/* ── body ── */}
              <div className="px-6 py-5">
                {loading || !summary ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-xs text-silver-400">
                      <Loader2 className="size-3.5 animate-spin" />
                      The Executive Briefing agent is reading every clause…
                    </div>
                    {Array.from({ length: 5 }).map((_, i) => (
                      <div key={i} className="space-y-2">
                        <Skeleton className="h-2.5 w-28" />
                        <Skeleton className="h-3 w-full" />
                        <Skeleton className="h-3 w-4/5" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-6">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="accent">{summary.overall_recommendation}</Badge>
                      <Badge variant="neutral" size="sm">
                        confidence {formatPct(summary.confidence)}
                      </Badge>
                      {summary.cached && (
                        <Badge variant="neutral" size="sm">
                          cached
                        </Badge>
                      )}
                    </div>

                    <p className="text-base font-medium leading-relaxed text-silver-100">
                      {summary.headline}
                    </p>

                    {/* exposure */}
                    <div className="rounded-lg border border-risk-high/25 bg-risk-high/[0.05] p-4">
                      <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-risk-high">
                        <Wallet className="size-3" /> Financial exposure
                      </p>
                      <p className="numeric text-2xl font-semibold text-risk-high">
                        {summary.financial_exposure?.headline_figure ?? "Not quantified"}
                      </p>
                      {summary.financial_exposure?.notes && (
                        <p className="mt-1.5 text-2xs leading-relaxed text-silver-400">
                          {summary.financial_exposure.notes}
                        </p>
                      )}
                    </div>

                    <BriefList
                      icon={<FileSignature className="size-3" />}
                      title="Key obligations"
                      items={summary.key_obligations}
                    />

                    <div className="grid gap-5 sm:grid-cols-2">
                      <BriefList
                        icon={<CalendarClock className="size-3" />}
                        title="Dates & deadlines"
                        items={summary.deadlines}
                      />
                      <div>
                        <p className="eyebrow mb-2">Renewal</p>
                        <p className="text-xs leading-relaxed text-silver-300">
                          {summary.renewal_terms || "—"}
                        </p>
                      </div>
                    </div>

                    {/* top risks */}
                    <div>
                      <p className="eyebrow mb-2.5">Top risks</p>
                      {summary.top_risks?.length ? (
                        <ul className="space-y-2">
                          {summary.top_risks.map((risk, i) => (
                            <li
                              key={`${risk.clause}-${i}`}
                              className="rounded-lg border border-silver-50/[0.06] bg-base-800/40 p-3"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-xs font-semibold text-silver-100">
                                  {risk.clause}
                                </p>
                                <Badge
                                  variant={
                                    risk.risk === "Critical"
                                      ? "critical"
                                      : risk.risk === "High"
                                        ? "high"
                                        : "medium"
                                  }
                                  size="sm"
                                >
                                  {risk.risk}
                                </Badge>
                              </div>
                              <p className="mt-1.5 text-2xs leading-relaxed text-silver-400">
                                {risk.why}
                              </p>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-silver-500">No high-risk clauses identified.</p>
                      )}
                    </div>

                    <BriefList
                      title="Recommended actions"
                      items={summary.recommended_actions}
                      numbered
                    />

                    <p className="border-t border-silver-50/[0.06] pt-4 text-[0.625rem] leading-relaxed text-silver-600">
                      Produced by an AI agent. This is a summary, not legal advice — and every
                      AI-proposed change still passes through the human approval gate before it is
                      finalised.
                    </p>
                  </div>
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

function BriefList({
  title,
  items,
  icon,
  numbered = false,
}: {
  title: string;
  items?: string[];
  icon?: React.ReactNode;
  numbered?: boolean;
}) {
  return (
    <div>
      <p className="eyebrow mb-2 flex items-center gap-1.5">
        {icon}
        {title}
      </p>
      {items?.length ? (
        <ul className="space-y-1.5">
          {items.map((item, i) => (
            <li key={i} className="flex gap-2.5 text-xs leading-relaxed text-silver-300">
              <span
                className={cn(
                  "shrink-0",
                  numbered ? "numeric font-semibold text-accent-soft" : "text-accent",
                )}
              >
                {numbered ? `${i + 1}.` : "•"}
              </span>
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-silver-500">None identified.</p>
      )}
    </div>
  );
}

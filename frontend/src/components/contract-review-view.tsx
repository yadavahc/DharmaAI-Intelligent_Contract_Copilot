"use client";

import {
  ArrowLeft,
  ChevronDown,
  FileText,
  Gavel,
  Loader2,
  Play,
  ShieldAlert,
  Sparkles,
  Swords,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import * as React from "react";
import { toast } from "sonner";

import { DiffView } from "@/components/diff-view";
import { ExecutiveSummaryPanel } from "@/components/executive-summary-panel";
import { GuardrailVerdictCard } from "@/components/guardrail-verdict";
import {
  AnimatedNumber,
  Collapse,
  PageTransition,
  Stagger,
  StaggerItem,
  ThinkingIndicator,
} from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  Progress,
  RiskBadge,
  Skeleton,
  SkeletonCard,
  Tooltip,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { Clause, Contract, ReviewEvent } from "@/lib/types";
import { cn, formatPct, riskClasses, truncate } from "@/lib/utils";

export function ContractReviewView({ contractId }: { contractId: string }) {
  const router = useRouter();
  const { data: session } = useSession();
  const role = session?.user?.role ?? "BUSINESS_USER";

  const [contract, setContract] = React.useState<Contract | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [reviewing, setReviewing] = React.useState(false);
  const [progress, setProgress] = React.useState<{ done: number; total: number; pct: number } | null>(
    null,
  );
  const [activeClause, setActiveClause] = React.useState<string | null>(null);
  const [liveResults, setLiveResults] = React.useState<Record<string, ReviewEvent>>({});
  const abortRef = React.useRef<AbortController | null>(null);

  const load = React.useCallback(async () => {
    try {
      setError(null);
      setContract(await api.contract(contractId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }, [contractId]);

  React.useEffect(() => {
    load();
  }, [load]);

  // Abort an in-flight stream if the user navigates away mid-review.
  React.useEffect(() => () => abortRef.current?.abort(), []);

  const runReview = async () => {
    setReviewing(true);
    setLiveResults({});
    setProgress({ done: 0, total: contract?.clause_count ?? 0, pct: 0 });

    const controller = new AbortController();
    abortRef.current = controller;

    await api.streamReview(contractId, {
      signal: controller.signal,
      onEvent: (event) => {
        switch (event.type) {
          case "start":
            setProgress({ done: 0, total: event.clause_count, pct: 0 });
            break;
          case "clause_started":
            setActiveClause(event.heading || `Clause ${event.index + 1}`);
            break;
          case "clause_done":
            setProgress(event.progress);
            setLiveResults((prev) => ({ ...prev, [event.clause_id]: event }));
            break;
          case "contract_done":
            setActiveClause(null);
            toast.success("Review complete", {
              description:
                `Contract risk ${event.risk.score}/100 (${event.risk.level}) · ` +
                `${event.escalated} clause(s) escalated to human review.`,
            });
            break;
          case "error":
            toast.error("Review error", { description: event.error });
            break;
        }
      },
      onError: (err) => {
        toast.error("Review stream failed", { description: err.message });
        setReviewing(false);
      },
      onDone: async () => {
        setReviewing(false);
        setActiveClause(null);
        await load();
      },
    });
  };

  const remove = async () => {
    if (!window.confirm(`Delete "${contract?.title}"? This cannot be undone.`)) return;
    try {
      await api.deleteContract(contractId);
      toast.success("Contract deleted");
      router.push("/contracts");
    } catch (err) {
      toast.error("Delete failed", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    }
  };

  if (error) {
    return (
      <Alert variant="danger" title="Could not load the contract" icon={<ShieldAlert className="size-4" />}>
        {error}
        <div className="mt-3 flex gap-2">
          <Button size="sm" variant="secondary" onClick={load}>
            Retry
          </Button>
          <Button size="sm" variant="ghost" asChild>
            <Link href="/contracts">Back to contracts</Link>
          </Button>
        </div>
      </Alert>
    );
  }

  if (!contract) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-2/3" />
        <div className="grid gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} lines={2} />
          ))}
        </div>
        <SkeletonCard lines={8} />
      </div>
    );
  }

  const reviewed = contract.risk_score > 0;
  const clauses = contract.clauses ?? [];
  const escalatedCount = clauses.filter(
    (c) => (c.escalation as { should_escalate?: boolean })?.should_escalate,
  ).length;
  const risk = riskClasses(contract.risk_level);

  return (
    <PageTransition className="space-y-6">
      {/* ── header ── */}
      <div>
        <Button variant="ghost" size="sm" asChild className="mb-3 -ml-2">
          <Link href="/contracts">
            <ArrowLeft className="size-3.5" /> Contracts
          </Link>
        </Button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow mb-1.5">Contract review</p>
            <h1 className="text-2xl font-semibold tracking-tight text-silver-50 sm:text-3xl">
              {contract.title}
            </h1>
            <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-silver-500">
              <span className="flex items-center gap-1.5">
                <FileText className="size-3" />
                {contract.filename}
              </span>
              {contract.counterparty && <span>vs. {contract.counterparty}</span>}
              <span>{contract.clause_count} clauses</span>
              {contract.page_count > 0 && <span>{contract.page_count} pages</span>}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {!reviewed && !reviewing && (
              <Button variant="primary" onClick={runReview} data-testid="run-review">
                <Play className="size-4" /> Run agent review
              </Button>
            )}
            {reviewed && !reviewing && (
              <Button variant="secondary" onClick={runReview} data-testid="rerun-review">
                <Play className="size-3.5" /> Re-run review
              </Button>
            )}
            {reviewing && (
              <Button variant="secondary" disabled>
                <Loader2 className="size-3.5 animate-spin" /> Reviewing…
              </Button>
            )}
            {role === "ADMIN" && (
              <Tooltip content="Delete contract (Admin only)">
                <Button variant="danger" size="icon" onClick={remove} aria-label="Delete contract">
                  <Trash2 />
                </Button>
              </Tooltip>
            )}
          </div>
        </div>
      </div>

      {/* ── live review progress ── */}
      {reviewing && progress && (
        <Card className="border-accent/25">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <ThinkingIndicator label={activeClause ? `analysing ${activeClause}` : "starting"} />
            </div>
            <span className="numeric text-xs text-silver-400">
              {progress.done} / {progress.total} clauses
            </span>
          </div>
          <Progress value={progress.pct} />
          <p className="mt-3 text-2xs leading-relaxed text-silver-500">
            Five agents run per clause: Classification → Playbook Validation → Risk Assessment →
            Redline → Escalation.
          </p>
        </Card>
      )}

      {/* ── KPI strip ── */}
      {reviewed && (
        <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StaggerItem>
            <Card>
              <p className="text-2xs uppercase tracking-wider text-silver-500">Contract risk</p>
              <p className={cn("numeric mt-2 text-3xl font-semibold", risk.text)}>
                <AnimatedNumber value={contract.risk_score} decimals={1} />
                <span className="text-sm text-silver-500">/100</span>
              </p>
              <RiskBadge level={contract.risk_level} size="sm" className="mt-2.5" />
            </Card>
          </StaggerItem>
          <StaggerItem>
            <Card>
              <p className="text-2xs uppercase tracking-wider text-silver-500">
                Escalated to human
              </p>
              <p className="numeric mt-2 text-3xl font-semibold text-risk-high">
                <AnimatedNumber value={escalatedCount} />
                <span className="text-sm text-silver-500">/{clauses.length}</span>
              </p>
              {escalatedCount > 0 && (
                <Button variant="ghost" size="sm" asChild className="mt-1.5 -ml-2">
                  <Link href="/review">Open review queue →</Link>
                </Button>
              )}
            </Card>
          </StaggerItem>
          <StaggerItem>
            <Card>
              <p className="text-2xs uppercase tracking-wider text-silver-500">
                Weighted mean
              </p>
              <p className="numeric mt-2 text-3xl font-semibold text-silver-100">
                <AnimatedNumber
                  value={(contract.risk_summary as { weighted_mean?: number })?.weighted_mean ?? 0}
                  decimals={1}
                />
              </p>
              <p className="mt-2 text-2xs text-silver-500">
                + {(contract.risk_summary as { severity_penalty?: number })?.severity_penalty ?? 0}{" "}
                severity concentration
              </p>
            </Card>
          </StaggerItem>
          <StaggerItem>
            <ExecutiveSummaryPanel contractId={contractId} contractTitle={contract.title} />
          </StaggerItem>
        </Stagger>
      )}

      {/* ── input guardrails ── */}
      {contract.guardrail_report?.verdicts?.length ? (
        <div>
          <p className="eyebrow mb-3">Input guardrail screening</p>
          <div className="grid gap-3 md:grid-cols-2">
            {contract.guardrail_report.verdicts.map((verdict) => (
              <GuardrailVerdictCard key={verdict.guardrail} verdict={verdict} compact />
            ))}
          </div>
        </div>
      ) : null}

      {/* ── clauses ── */}
      <div>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow mb-1">Clause-by-clause</p>
            <h2 className="text-lg font-semibold text-silver-100">
              {clauses.length} clause{clauses.length === 1 ? "" : "s"}
            </h2>
          </div>
          {reviewed && (
            <p className="text-2xs text-silver-500">
              Sorted by document order · click any clause to expand
            </p>
          )}
        </div>

        {clauses.length === 0 ? (
          <EmptyState title="No clauses" description="This contract produced no clauses." />
        ) : !reviewed && !reviewing ? (
          <Card className="border-accent/20 bg-accent/[0.03]">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <CardTitle>Not reviewed yet</CardTitle>
                <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-silver-400">
                  {clauses.length} clauses are extracted and embedded. Run the agent review to
                  classify each one, score it against the playbook, and draft redlines.
                </p>
              </div>
              <Button variant="primary" onClick={runReview}>
                <Play className="size-4" /> Run agent review
              </Button>
            </div>
          </Card>
        ) : (
          <div className="space-y-2.5">
            {clauses.map((clause) => (
              <ClauseRow
                key={clause.id}
                clause={clause}
                live={liveResults[clause.id]}
                reviewing={reviewing}
              />
            ))}
          </div>
        )}
      </div>
    </PageTransition>
  );
}

/* ── clause row ─────────────────────────────────────────────────────────── */

function ClauseRow({
  clause,
  live,
  reviewing,
}: {
  clause: Clause;
  live?: ReviewEvent;
  reviewing: boolean;
}) {
  const [open, setOpen] = React.useState(false);

  // While a review is streaming, prefer the live event over the stale stored row.
  const liveDone = live?.type === "clause_done" ? live : null;
  const category = liveDone?.category ?? clause.category;
  const riskScore = liveDone?.risk_score ?? clause.risk_score;
  const riskLevel = liveDone?.risk_level ?? clause.risk_level;
  const confidence = liveDone?.confidence ?? clause.confidence;
  const explanation = liveDone?.explanation ?? clause.explanation;
  const escalated =
    liveDone?.escalated ?? (clause.escalation as { should_escalate?: boolean })?.should_escalate;

  const scored = riskScore > 0;
  const risk = riskClasses(riskLevel);
  const redline = clause.redline ?? {};
  const hasRedline = Boolean(redline.suggested && redline.suggested !== clause.text);
  const violations = (clause.playbook as { violations?: unknown[] })?.violations ?? [];

  const lowConfidence = confidence > 0 && confidence < 0.7;

  return (
    <Card
      flush
      className={cn(
        "overflow-hidden transition-colors",
        escalated && "border-risk-high/25",
        reviewing && !scored && "opacity-60",
      )}
      data-testid="clause-row"
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-base-800/40"
        aria-expanded={open}
      >
        <span
          className={cn(
            "numeric mt-0.5 grid size-10 shrink-0 place-items-center rounded-lg text-sm font-bold",
            scored ? `${risk.bg} ${risk.text}` : "bg-base-700/50 text-silver-500",
          )}
        >
          {scored ? Math.round(riskScore) : clause.index + 1}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-silver-100">
              {clause.label && <span className="text-silver-500">{clause.label} </span>}
              {clause.heading || `Clause ${clause.index + 1}`}
            </p>
            {scored && <Badge variant="neutral" size="sm">{category}</Badge>}
            {scored && <RiskBadge level={riskLevel} size="sm" />}
            {escalated && (
              <Badge variant="high" size="sm">
                <Gavel className="size-2.5" /> escalated
              </Badge>
            )}
            {hasRedline && (
              <Badge variant="accent" size="sm">
                redline
              </Badge>
            )}
            {violations.length > 0 && (
              <Badge variant="critical" size="sm">
                {violations.length} rule breach{violations.length === 1 ? "" : "es"}
              </Badge>
            )}
            {lowConfidence && (
              <Tooltip content="Below the 70% confidence threshold — flagged by the hallucination guardrail">
                <Badge variant="medium" size="sm">
                  low confidence {formatPct(confidence)}
                </Badge>
              </Tooltip>
            )}
          </div>
          <p className="mt-1.5 line-clamp-2 text-2xs leading-relaxed text-silver-500">
            {scored && explanation ? truncate(explanation, 190) : truncate(clause.text, 190)}
          </p>
        </div>

        <ChevronDown
          className={cn(
            "mt-1 size-4 shrink-0 text-silver-500 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>

      <Collapse open={open}>
        <div className="space-y-5 border-t border-silver-50/[0.06] px-4 py-4">
          {/* clause text */}
          <div>
            <p className="eyebrow mb-2">Clause text</p>
            <p className="whitespace-pre-wrap rounded-lg border border-silver-50/[0.06] bg-base-900/50 p-3.5 font-mono text-xs leading-relaxed text-silver-300">
              {clause.text}
            </p>
          </div>

          {/* risk explanation */}
          {scored && explanation && (
            <div>
              <p className="eyebrow mb-2">Risk assessment</p>
              <p className="text-xs leading-relaxed text-silver-300">{explanation}</p>
              {clause.suggested_fix && (
                <div className="mt-3 rounded-lg border border-accent/20 bg-accent/[0.04] p-3">
                  <p className="mb-1 text-2xs font-semibold uppercase tracking-wider text-accent-soft">
                    Suggested fix
                  </p>
                  <p className="text-xs leading-relaxed text-silver-300">{clause.suggested_fix}</p>
                </div>
              )}
            </div>
          )}

          {/* playbook violations */}
          {violations.length > 0 && (
            <div>
              <p className="eyebrow mb-2">Playbook breaches</p>
              <ul className="space-y-1.5">
                {(violations as { rule_id: string; detail: string; severity: string }[]).map((v) => (
                  <li
                    key={v.rule_id}
                    className="flex items-start gap-2 rounded-md border border-risk-critical/20 bg-risk-critical/[0.05] p-2.5"
                  >
                    <code className="shrink-0 font-mono text-[0.625rem] font-bold text-risk-critical">
                      {v.rule_id}
                    </code>
                    <span className="text-2xs leading-relaxed text-silver-300">{v.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* redline diff */}
          {hasRedline && (
            <DiffView
              original={redline.original ?? clause.text}
              suggested={redline.suggested ?? ""}
              reason={redline.reason}
              changeSummary={redline.change_summary}
            />
          )}

          {/* agent trace */}
          {clause.agent_trace?.length > 0 && (
            <div>
              <p className="eyebrow mb-2">Agent trace</p>
              <div className="flex flex-wrap gap-1.5">
                {clause.agent_trace.map((entry, i) => (
                  <span
                    key={`${entry.agent}-${i}`}
                    className="flex items-center gap-1.5 rounded-md border border-silver-50/[0.06] bg-base-900/50 px-2 py-1"
                  >
                    <span className="text-[0.625rem] text-silver-300">{entry.agent}</span>
                    <span className="numeric text-[0.625rem] text-silver-600">
                      {entry.duration_ms}ms
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* actions */}
          <div className="flex flex-wrap gap-2 border-t border-silver-50/[0.06] pt-4">
            <Button variant="secondary" size="sm" asChild>
              <Link href={`/clauses/${clause.id}`}>
                <Sparkles className="size-3.5" /> Open clause workspace
              </Link>
            </Button>
            {scored && (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/negotiations/${clause.id}`}>
                  <Swords className="size-3.5" /> Negotiate this clause
                </Link>
              </Button>
            )}
          </div>
        </div>
      </Collapse>
    </Card>
  );
}

"use client";

import {
  ArrowLeft,
  ArrowUpRight,
  Copy,
  Database,
  History,
  Library,
  RotateCcw,
  ShieldAlert,
  Swords,
} from "lucide-react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import * as React from "react";
import { toast } from "sonner";

import { DiffView, VersionDiff } from "@/components/diff-view";
import { GuardrailVerdictCard } from "@/components/guardrail-verdict";
import { RiskSimulator } from "@/components/risk-simulator";
import {
  AnimatedNumber,
  Collapse,
  PageTransition,
} from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  Input,
  RiskBadge,
  Skeleton,
  SkeletonCard,
  Tooltip,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { Clause, Precedent, SearchResult } from "@/lib/types";
import { canApprove, cn, formatDateTime, formatPct, riskClasses, truncate } from "@/lib/utils";

export function ClauseWorkspace({ clauseId }: { clauseId: string }) {
  const { data: session } = useSession();
  const role = session?.user?.role;

  const [clause, setClause] = React.useState<Clause | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [precedents, setPrecedents] = React.useState<Precedent[] | null>(null);
  const [precedentNote, setPrecedentNote] = React.useState("");
  const [similar, setSimilar] = React.useState<SearchResult[] | null>(null);

  const load = React.useCallback(async () => {
    try {
      setError(null);
      setClause(await api.clause(clauseId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }, [clauseId]);

  React.useEffect(() => {
    load();
  }, [load]);

  // Qdrant retrieval roles 2 and 4, fetched in parallel once the clause loads.
  React.useEffect(() => {
    if (!clause) return;
    api
      .clausePrecedents(clauseId, 3)
      .then((r) => {
        setPrecedents(r.precedents);
        setPrecedentNote(r.note);
      })
      .catch(() => setPrecedents([]));
    api
      .similarClauses(clauseId, 5)
      .then((r) => setSimilar(r.similar_clauses))
      .catch(() => setSimilar([]));
  }, [clause, clauseId]);

  if (error) {
    return (
      <Alert variant="danger" title="Could not load the clause" icon={<ShieldAlert className="size-4" />}>
        {error}
        <div className="mt-3">
          <Button size="sm" variant="secondary" onClick={load}>
            Retry
          </Button>
        </div>
      </Alert>
    );
  }

  if (!clause) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-8 w-1/2" />
        <div className="grid gap-4 lg:grid-cols-3">
          <SkeletonCard lines={6} className="lg:col-span-2" />
          <SkeletonCard lines={6} />
        </div>
      </div>
    );
  }

  const risk = riskClasses(clause.risk_level);
  const redline = clause.redline ?? {};
  const hasRedline = Boolean(redline.suggested && redline.suggested !== clause.text);
  const violations =
    ((clause.playbook as { violations?: { rule_id: string; detail: string }[] })?.violations) ?? [];
  const guardrailVerdicts = Object.values(clause.guardrails ?? {}).flatMap(
    (entry) => entry?.verdicts ?? [],
  );

  return (
    <PageTransition className="space-y-6">
      {/* ── header ── */}
      <div>
        <Button variant="ghost" size="sm" asChild className="mb-3 -ml-2">
          <Link href={`/contracts/${clause.contract_id}`}>
            <ArrowLeft className="size-3.5" /> {truncate(clause.contract_title, 44) || "Contract"}
          </Link>
        </Button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow mb-1.5">Clause workspace</p>
            <h1 className="text-2xl font-semibold tracking-tight text-silver-50">
              {clause.label && <span className="text-silver-500">{clause.label} </span>}
              {clause.heading || `Clause ${clause.index + 1}`}
            </h1>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge variant="neutral" size="sm">
                {clause.category}
              </Badge>
              <RiskBadge level={clause.risk_level} score={clause.risk_score} size="sm" />
              <Badge
                variant={clause.confidence < 0.7 ? "medium" : "neutral"}
                size="sm"
              >
                confidence {formatPct(clause.confidence)}
              </Badge>
              <Badge
                variant={clause.approval_state === "finalized" ? "low" : "medium"}
                size="sm"
              >
                {clause.approval_state.replace(/_/g, " ")}
              </Badge>
            </div>
          </div>

          <Button variant="outline" asChild>
            <Link href={`/negotiations/${clause.id}`}>
              <Swords className="size-4" /> Negotiate
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* ── left column ── */}
        <div className="space-y-5 lg:col-span-2">
          {/* current text */}
          <Card>
            <div className="mb-3 flex items-start justify-between gap-3">
              <CardTitle>Current text (v{clause.current_version})</CardTitle>
              <Tooltip content="Copy clause text">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => {
                    navigator.clipboard.writeText(clause.text);
                    toast.success("Copied");
                  }}
                  aria-label="Copy clause text"
                >
                  <Copy className="size-3.5" />
                </Button>
              </Tooltip>
            </div>
            <p className="whitespace-pre-wrap rounded-lg border border-silver-50/[0.06] bg-base-900/50 p-4 font-mono text-xs leading-relaxed text-silver-300">
              {clause.text}
            </p>
          </Card>

          {/* risk assessment */}
          {clause.explanation && (
            <Card>
              <CardTitle className="mb-3">Risk assessment</CardTitle>
              <div className="mb-4 flex items-center gap-4">
                <div>
                  <p className={cn("numeric text-4xl font-semibold", risk.text)}>
                    <AnimatedNumber value={clause.risk_score} decimals={1} />
                  </p>
                  <p className="mt-0.5 text-2xs text-silver-500">out of 100</p>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs leading-relaxed text-silver-300">{clause.explanation}</p>
                </div>
              </div>

              {clause.suggested_fix && (
                <div className="rounded-lg border border-accent/20 bg-accent/[0.04] p-3.5">
                  <p className="mb-1.5 text-2xs font-semibold uppercase tracking-wider text-accent-soft">
                    Suggested fix
                  </p>
                  <p className="text-xs leading-relaxed text-silver-300">{clause.suggested_fix}</p>
                </div>
              )}

              {/* score composition */}
              {clause.risk && (
                <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-silver-50/[0.06] pt-4 sm:grid-cols-4">
                  {[
                    { label: "Blended", value: clause.risk_score },
                    { label: "Model", value: (clause.risk as { llm_score?: number }).llm_score },
                    {
                      label: "Deterministic",
                      value: (clause.risk as { deterministic_score?: number }).deterministic_score,
                    },
                    {
                      label: "Rules fired",
                      value: ((clause.risk as { triggered_rule_ids?: string[] }).triggered_rule_ids ?? [])
                        .length,
                    },
                  ].map((item) => (
                    <div key={item.label}>
                      <dt className="text-[0.625rem] uppercase tracking-wider text-silver-600">
                        {item.label}
                      </dt>
                      <dd className="numeric mt-0.5 text-sm font-semibold text-silver-200">
                        {item.value ?? "—"}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
              <p className="mt-3 text-[0.625rem] leading-relaxed text-silver-600">
                The score blends the model&apos;s judgement (60%) with deterministic policy
                arithmetic (40%). A fired playbook rule sets a High-risk floor regardless of the
                model&apos;s opinion.
              </p>
            </Card>
          )}

          {/* playbook breaches */}
          {violations.length > 0 && (
            <Card className="border-risk-critical/20">
              <CardTitle className="mb-3">Playbook breaches</CardTitle>
              <ul className="space-y-2">
                {violations.map((v) => (
                  <li
                    key={v.rule_id}
                    className="flex items-start gap-2.5 rounded-md border border-risk-critical/20 bg-risk-critical/[0.05] p-3"
                  >
                    <code className="shrink-0 font-mono text-[0.625rem] font-bold text-risk-critical">
                      {v.rule_id}
                    </code>
                    <span className="text-2xs leading-relaxed text-silver-300">{v.detail}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {/* redline */}
          {hasRedline && (
            <Card>
              <DiffView
                original={redline.original ?? clause.text}
                suggested={redline.suggested ?? ""}
                reason={redline.reason}
                changeSummary={redline.change_summary}
              />
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-silver-50/[0.06] pt-4">
                <Badge variant={redline.materiality === "high" ? "high" : "neutral"} size="sm">
                  {redline.materiality} materiality
                </Badge>
                <Badge variant="neutral" size="sm">
                  confidence {formatPct(redline.confidence)}
                </Badge>
                {redline.used_precedent && (
                  <Badge variant="accent" size="sm">
                    <Library className="size-2.5" /> used {redline.precedent_count} precedent
                    {redline.precedent_count === 1 ? "" : "s"}
                  </Badge>
                )}
                <span className="ml-auto text-2xs text-silver-500">
                  Awaiting human approval — see the{" "}
                  <Link href="/review" className="text-accent-soft underline underline-offset-2">
                    review queue
                  </Link>
                </span>
              </div>
            </Card>
          )}

          {/* Feature 2 — Risk Simulator */}
          <RiskSimulator
            contractId={clause.contract_id}
            clauseId={clause.id}
            initialText={clause.text}
            baselineScore={clause.risk_score}
          />

          {/* version history */}
          <VersionHistory
            clauseId={clause.id}
            canRollback={canApprove(role)}
            onRolledBack={load}
          />

          {/* guardrails */}
          {guardrailVerdicts.length > 0 && (
            <div>
              <p className="eyebrow mb-3">Output guardrails on this clause</p>
              <div className="space-y-3">
                {guardrailVerdicts.map((verdict, i) => (
                  <GuardrailVerdictCard
                    key={`${verdict.guardrail}-${i}`}
                    verdict={verdict}
                    compact
                    defaultOpen={false}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── right column ── */}
        <div className="space-y-5">
          {/* Feature 4 — Precedent Recall */}
          <Card>
            <div className="mb-1 flex items-center gap-2">
              <Library className="size-3.5 text-accent" />
              <CardTitle>Precedent Recall</CardTitle>
            </div>
            <p className="mb-4 text-2xs leading-relaxed text-silver-500">
              Closest previously <strong className="text-silver-400">approved</strong> wording, from
              the Qdrant precedent library.
            </p>

            {precedents === null ? (
              <div className="space-y-3">
                {Array.from({ length: 2 }).map((_, i) => (
                  <div key={i} className="space-y-2">
                    <Skeleton className="h-2.5 w-20" />
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-3 w-3/4" />
                  </div>
                ))}
              </div>
            ) : precedents.length === 0 ? (
              <EmptyState
                title="No close precedent"
                description="No approved clause in this category was similar enough. Approving a redline adds it here."
                className="border-0 py-6"
              />
            ) : (
              <ul className="space-y-3">
                {precedents.map((precedent) => (
                  <li
                    key={precedent.id}
                    className="rounded-lg border border-silver-50/[0.06] bg-base-900/40 p-3"
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <Badge variant="accent" size="sm">
                        {precedent.similarity_pct ?? Math.round(precedent.score * 100)}% match
                      </Badge>
                      <span className="truncate text-[0.625rem] text-silver-600">
                        {precedent.contract_title}
                      </span>
                    </div>
                    <p className="line-clamp-5 font-mono text-2xs leading-relaxed text-silver-300">
                      {precedent.text}
                    </p>
                    <div className="mt-2.5 flex items-center justify-between gap-2">
                      {precedent.approved_by && (
                        <span className="truncate text-[0.625rem] text-silver-600">
                          approved by {precedent.approved_by}
                        </span>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="-mr-2 shrink-0"
                        onClick={() => {
                          navigator.clipboard.writeText(precedent.text);
                          toast.success("Recommended language copied");
                        }}
                      >
                        <Copy className="size-3" /> Copy
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {precedentNote && (
              <p className="mt-3 border-t border-silver-50/[0.06] pt-3 text-[0.625rem] leading-relaxed text-silver-600">
                {precedentNote}
              </p>
            )}
          </Card>

          {/* similar clauses */}
          <Card>
            <div className="mb-1 flex items-center gap-2">
              <Database className="size-3.5 text-accent" />
              <CardTitle>Similar clauses</CardTitle>
            </div>
            <p className="mb-4 text-2xs leading-relaxed text-silver-500">
              Comparable {clause.category} clauses in other contracts.
            </p>

            {similar === null ? (
              <div className="space-y-2">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-4/5" />
              </div>
            ) : similar.length === 0 ? (
              <p className="py-4 text-center text-2xs text-silver-500">
                No comparable clause found in another contract yet.
              </p>
            ) : (
              <ul className="space-y-2.5">
                {similar.map((hit) => (
                  <li key={hit.id}>
                    <Link
                      href={hit.clause_id ? `/clauses/${hit.clause_id}` : "#"}
                      className="group block rounded-md border border-silver-50/[0.06] bg-base-900/40 p-2.5 transition-colors hover:border-accent/25"
                    >
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <span className="numeric text-[0.625rem] text-accent-soft">
                          {(hit.score * 100).toFixed(0)}%
                        </span>
                        <span className="flex items-center gap-1 truncate text-[0.625rem] text-silver-600">
                          {truncate(hit.contract_title, 24)}
                          <ArrowUpRight className="size-2.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
                        </span>
                      </div>
                      <p className="line-clamp-3 text-2xs leading-relaxed text-silver-400">
                        {hit.text}
                      </p>
                      {hit.risk_level && (
                        <RiskBadge level={hit.risk_level} size="sm" className="mt-2" />
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </PageTransition>
  );
}

/* ── version history ────────────────────────────────────────────────────── */

const SOURCE_LABELS: Record<string, { label: string; variant: "neutral" | "accent" | "low" | "medium" }> = {
  original: { label: "Original", variant: "neutral" },
  ai_redline: { label: "AI redline", variant: "accent" },
  negotiation: { label: "Negotiated", variant: "medium" },
  human_edit: { label: "Human edit", variant: "low" },
  rollback: { label: "Rollback", variant: "medium" },
};

function VersionHistory({
  clauseId,
  canRollback,
  onRolledBack,
}: {
  clauseId: string;
  canRollback: boolean;
  onRolledBack: () => void;
}) {
  const [data, setData] = React.useState<Awaited<ReturnType<typeof api.clauseVersions>> | null>(null);
  const [expanded, setExpanded] = React.useState<number | null>(null);
  const [rollingBack, setRollingBack] = React.useState<number | null>(null);
  const [reason, setReason] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      setData(await api.clauseVersions(clauseId));
    } catch {
      setData(null);
    }
  }, [clauseId]);

  React.useEffect(() => {
    load();
  }, [load]);

  const rollback = async (versionNo: number) => {
    setRollingBack(versionNo);
    try {
      await api.rollbackClause(clauseId, versionNo, reason);
      toast.success(`Rolled back to v${versionNo}`, {
        description: "A new version was appended — history is preserved.",
      });
      setReason("");
      setExpanded(null);
      await load();
      onRolledBack();
    } catch (err) {
      toast.error("Rollback failed", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    } finally {
      setRollingBack(null);
    }
  };

  if (!data) return <SkeletonCard lines={4} />;

  return (
    <Card>
      <div className="mb-1 flex items-center gap-2">
        <History className="size-3.5 text-accent" />
        <CardTitle>Version history</CardTitle>
        <Badge variant="neutral" size="sm" className="ml-auto">
          {data.versions.length} version{data.versions.length === 1 ? "" : "s"}
        </Badge>
      </div>
      <p className="mb-4 text-2xs leading-relaxed text-silver-500">
        Append-only. A rollback adds a new version rather than deleting history, so the audit trail
        still shows what was reverted.
      </p>

      <ol className="relative space-y-3 border-l border-silver-50/[0.08] pl-5">
        {[...data.versions].reverse().map((version) => {
          const isCurrent = version.version_no === data.current_version;
          const previous = data.versions.find((v) => v.version_no === version.version_no - 1);
          const meta = SOURCE_LABELS[version.source] ?? SOURCE_LABELS.original;
          const isOpen = expanded === version.version_no;

          return (
            <li key={version.version_no} className="relative">
              <span
                className={cn(
                  "absolute -left-[1.575rem] top-1.5 size-2.5 rounded-full ring-4 ring-base-800",
                  isCurrent ? "bg-accent" : "bg-silver-600",
                )}
              />
              <button
                type="button"
                onClick={() => setExpanded(isOpen ? null : version.version_no)}
                className="w-full rounded-md text-left transition-colors hover:bg-base-800/40"
                aria-expanded={isOpen}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="numeric text-xs font-semibold text-silver-100">
                    v{version.version_no}
                  </span>
                  <Badge variant={meta.variant} size="sm">
                    {meta.label}
                  </Badge>
                  {isCurrent && (
                    <Badge variant="low" size="sm">
                      current
                    </Badge>
                  )}
                  <span className="text-[0.625rem] text-silver-600">
                    {formatDateTime(version.created_at)} · {version.author}
                  </span>
                </div>
                {version.reason && (
                  <p className="mt-1 line-clamp-2 text-2xs leading-relaxed text-silver-500">
                    {version.reason}
                  </p>
                )}
              </button>

              <Collapse open={isOpen}>
                <div className="mt-2.5 space-y-3">
                  {previous ? (
                    <div>
                      <p className="mb-1.5 text-[0.625rem] uppercase tracking-wider text-silver-600">
                        Changes from v{previous.version_no}
                      </p>
                      <VersionDiff fromText={previous.text} toText={version.text} />
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap rounded-md border border-silver-50/[0.06] bg-base-900/50 p-3 font-mono text-2xs leading-relaxed text-silver-400">
                      {version.text}
                    </p>
                  )}

                  {!isCurrent && (
                    <div className="rounded-md border border-silver-50/[0.06] bg-base-900/40 p-3">
                      {canRollback ? (
                        <>
                          <Input
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            placeholder="Reason for rolling back (recorded in the audit log)"
                            className="mb-2.5 h-9 text-xs"
                          />
                          <Button
                            variant="secondary"
                            size="sm"
                            loading={rollingBack === version.version_no}
                            onClick={() => rollback(version.version_no)}
                          >
                            <RotateCcw className="size-3.5" /> Roll back to v{version.version_no}
                          </Button>
                        </>
                      ) : (
                        <p className="text-2xs text-silver-500">
                          Rollback requires the Reviewer or Admin role.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </Collapse>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

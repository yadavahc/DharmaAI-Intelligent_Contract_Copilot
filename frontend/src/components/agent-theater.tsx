"use client";

import {
  ArrowLeft,
  Brain,
  Building2,
  CheckCircle2,
  Gavel,
  Handshake,
  Lightbulb,
  Play,
  Scale,
  Square,
  TrendingDown,
  Users,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  AnimatePresence,
  AnimatedNumber,
  PageTransition,
  PulseDot,
  ThinkingIndicator,
  motion,
} from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  RiskBadge,
  Select,
  Skeleton,
  SkeletonCard,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type {
  Clause,
  Coaching,
  NegotiationEvent,
  NegotiationSide,
  NegotiationTurn,
} from "@/lib/types";
import { cn, formatPct, riskClasses, truncate } from "@/lib/utils";

/**
 * Feature 1 — Live Agent Theater. Feature 3 — Strategy Coach side panel.
 *
 * Renders the two negotiators as opposing seats, streaming their messages over
 * SSE with a round counter and a live risk gauge. The Coach panel updates after
 * each of our turns with an acceptance probability and a recommended next move.
 *
 * The stream is the source of truth while running; on completion the page reloads
 * the persisted negotiation so a refresh shows the same thing.
 */

type Phase = "idle" | "running" | "complete" | "error";

interface Seat {
  role: string;
  persona: string;
}

export function AgentTheater({ clauseId }: { clauseId: string }) {
  const [clause, setClause] = React.useState<Clause | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const [phase, setPhase] = React.useState<Phase>("idle");
  const [maxRounds, setMaxRounds] = React.useState(4);
  const [turns, setTurns] = React.useState<NegotiationTurn[]>([]);
  const [thinking, setThinking] = React.useState<{ side: NegotiationSide; role: string } | null>(
    null,
  );
  const [risk, setRisk] = React.useState<number | null>(null);
  const [initialRisk, setInitialRisk] = React.useState<number | null>(null);
  const [coaching, setCoaching] = React.useState<(Coaching & { round: number })[]>([]);
  const [seats, setSeats] = React.useState<Record<NegotiationSide, Seat> | null>(null);
  const [outcome, setOutcome] = React.useState<{ outcome: string; reason: string } | null>(null);
  const [escalation, setEscalation] = React.useState<Record<string, unknown> | null>(null);
  const [summary, setSummary] = React.useState<Record<string, unknown> | null>(null);
  const [memoryHits, setMemoryHits] = React.useState(0);
  const [streamError, setStreamError] = React.useState<string | null>(null);

  const abortRef = React.useRef<AbortController | null>(null);
  const transcriptRef = React.useRef<HTMLDivElement>(null);

  const load = React.useCallback(async () => {
    try {
      const data = await api.clause(clauseId);
      setClause(data);
      setRisk(data.risk_score);
      setInitialRisk(data.risk_score);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : String(err));
    }
  }, [clauseId]);

  React.useEffect(() => {
    load();
  }, [load]);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  // Keep the newest turn in view as the transcript grows.
  React.useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns.length, thinking]);

  const start = async () => {
    setPhase("running");
    setTurns([]);
    setCoaching([]);
    setOutcome(null);
    setEscalation(null);
    setSummary(null);
    setStreamError(null);
    setRisk(clause?.risk_score ?? 0);
    setInitialRisk(clause?.risk_score ?? 0);

    const controller = new AbortController();
    abortRef.current = controller;

    await api.streamNegotiation(
      clauseId,
      { maxRounds, includeCoach: true },
      {
        signal: controller.signal,
        onEvent: (event: NegotiationEvent) => {
          switch (event.type) {
            case "meta":
              setMemoryHits(event.memory_hits);
              break;
            case "start":
              setSeats(event.agents);
              setInitialRisk(event.initial_risk_score);
              setRisk(event.initial_risk_score);
              break;
            case "thinking":
              setThinking({ side: event.side, role: event.agent_role });
              break;
            case "turn":
              setThinking(null);
              setTurns((prev) => [...prev, event as unknown as NegotiationTurn]);
              break;
            case "risk":
              setRisk(event.risk_score);
              break;
            case "coach":
              setCoaching((prev) => [...prev, event as Coaching & { round: number }]);
              break;
            case "outcome":
              setOutcome({ outcome: event.outcome, reason: event.reason });
              break;
            case "escalation":
              setEscalation(event as unknown as Record<string, unknown>);
              break;
            case "done":
              setSummary(event as unknown as Record<string, unknown>);
              setRisk(event.final_risk_score);
              break;
            case "error":
              setStreamError(event.error);
              break;
          }
        },
        onError: (err) => {
          setStreamError(err.message);
          setPhase("error");
          setThinking(null);
          toast.error("Negotiation stream failed", { description: err.message });
        },
        onDone: async () => {
          setThinking(null);
          setPhase("complete");
          await load();
        },
      },
    );
  };

  const stop = () => {
    abortRef.current?.abort();
    setThinking(null);
    setPhase("idle");
    toast.info("Negotiation stopped");
  };

  if (loadError) {
    return (
      <Alert variant="danger" title="Could not load the clause">
        {loadError}
      </Alert>
    );
  }

  if (!clause) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-8 w-1/2" />
        <SkeletonCard lines={8} />
      </div>
    );
  }

  const latestCoaching = coaching[coaching.length - 1];
  const riskDelta = initialRisk !== null && risk !== null ? risk - initialRisk : 0;
  const currentRound = turns.length ? Math.max(...turns.map((t) => t.round)) : 0;

  return (
    <PageTransition className="space-y-6">
      {/* ── header ── */}
      <div>
        <Button variant="ghost" size="sm" asChild className="mb-3 -ml-2">
          <Link href={`/clauses/${clauseId}`}>
            <ArrowLeft className="size-3.5" /> Clause workspace
          </Link>
        </Button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow mb-1.5">Live Agent Theater</p>
            <h1 className="text-2xl font-semibold tracking-tight text-silver-50">
              {clause.heading || `Clause ${clause.index + 1}`}
            </h1>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge variant="neutral" size="sm">
                {clause.category}
              </Badge>
              <RiskBadge level={clause.risk_level} score={clause.risk_score} size="sm" />
              {memoryHits > 0 && (
                <Badge variant="accent" size="sm">
                  {memoryHits} negotiation memor{memoryHits === 1 ? "y" : "ies"} recalled
                </Badge>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label
                htmlFor="rounds"
                className="mb-1 block text-[0.625rem] uppercase tracking-wider text-silver-500"
              >
                Max rounds
              </label>
              <Select
                id="rounds"
                value={maxRounds}
                onChange={(e) => setMaxRounds(Number(e.target.value))}
                disabled={phase === "running"}
                className="h-9 w-24 text-xs"
              >
                {[2, 3, 4, 5, 6].map((n) => (
                  <option key={n} value={n}>
                    {n} rounds
                  </option>
                ))}
              </Select>
            </div>
            {phase === "running" ? (
              <Button variant="danger" onClick={stop}>
                <Square className="size-3.5" /> Stop
              </Button>
            ) : (
              <Button variant="primary" onClick={start} data-testid="start-negotiation">
                <Play className="size-4" />
                {phase === "complete" ? "Run again" : "Start negotiation"}
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* ── live risk gauge ── */}
      <Card className={cn(phase === "running" && "border-accent/25")}>
        <div className="flex flex-wrap items-center justify-between gap-5">
          <div className="flex items-center gap-5">
            <div>
              <p className="text-2xs uppercase tracking-wider text-silver-500">Live risk score</p>
              <div className="mt-1 flex items-baseline gap-2">
                <p
                  className={cn(
                    "numeric text-4xl font-semibold transition-colors duration-500",
                    riskClasses(
                      risk === null
                        ? clause.risk_level
                        : risk >= 90
                          ? "Critical"
                          : risk >= 70
                            ? "High"
                            : risk >= 40
                              ? "Medium"
                              : "Low",
                    ).text,
                  )}
                  data-testid="live-risk-score"
                >
                  <AnimatedNumber value={risk ?? clause.risk_score} decimals={1} />
                </p>
                {riskDelta !== 0 && (
                  <span
                    className={cn(
                      "numeric flex items-center gap-0.5 text-sm font-semibold",
                      riskDelta < 0 ? "text-risk-low" : "text-risk-critical",
                    )}
                  >
                    <TrendingDown
                      className={cn("size-3.5", riskDelta > 0 && "rotate-180")}
                    />
                    {riskDelta > 0 ? "+" : ""}
                    {riskDelta.toFixed(1)}
                  </span>
                )}
              </div>
            </div>

            <div className="hidden sm:block">
              <p className="text-2xs uppercase tracking-wider text-silver-500">Round</p>
              <p className="numeric mt-1 text-4xl font-semibold text-silver-100">
                {currentRound}
                <span className="text-lg text-silver-500">/{maxRounds}</span>
              </p>
            </div>
          </div>

          <div className="min-w-48 flex-1">
            {/* Gauge track with the starting position marked, so movement is legible. */}
            <div className="relative h-2 overflow-hidden rounded-full bg-base-700/70">
              <motion.div
                className={cn(
                  "h-full rounded-full",
                  (risk ?? 0) >= 90
                    ? "bg-risk-critical"
                    : (risk ?? 0) >= 70
                      ? "bg-risk-high"
                      : (risk ?? 0) >= 40
                        ? "bg-risk-medium"
                        : "bg-risk-low",
                )}
                animate={{ width: `${risk ?? 0}%` }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              />
              {initialRisk !== null && (
                <span
                  className="absolute top-0 h-full w-0.5 bg-silver-200/60"
                  style={{ left: `${initialRisk}%` }}
                  title={`Started at ${initialRisk.toFixed(1)}`}
                />
              )}
            </div>
            <div className="mt-2 flex items-center justify-between text-[0.625rem] text-silver-600">
              <span>0 — no risk</span>
              {phase === "running" && (
                <span className="flex items-center gap-1.5 text-accent">
                  <PulseDot /> streaming
                </span>
              )}
              <span>100 — existential</span>
            </div>
          </div>
        </div>
      </Card>

      {streamError && (
        <Alert variant="danger" title="Stream error">
          {streamError}
        </Alert>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {/* ── the theater ── */}
        <div className="space-y-4 lg:col-span-2">
          {/* seats */}
          <div className="grid grid-cols-2 gap-3">
            <SeatCard
              side="organization"
              seat={seats?.organization}
              active={thinking?.side === "organization"}
              turnCount={turns.filter((t) => t.side === "organization").length}
            />
            <SeatCard
              side="counterparty"
              seat={seats?.counterparty}
              active={thinking?.side === "counterparty"}
              turnCount={turns.filter((t) => t.side === "counterparty").length}
            />
          </div>

          {/* transcript */}
          <Card flush className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-silver-50/[0.06] px-4 py-3">
              <CardTitle>Transcript</CardTitle>
              {turns.length > 0 && (
                <span className="numeric text-2xs text-silver-500">{turns.length} turns</span>
              )}
            </div>

            <div
              ref={transcriptRef}
              className="max-h-[36rem] space-y-4 overflow-y-auto px-4 py-4"
              data-testid="negotiation-transcript"
            >
              {turns.length === 0 && !thinking && phase === "idle" && (
                <EmptyState
                  icon={<Users className="size-5" />}
                  title="No negotiation yet"
                  description="Start the negotiation to watch the Organization Agent and Counterparty Agent exchange positions in real time."
                  className="border-0"
                />
              )}

              <AnimatePresence initial={false}>
                {turns.map((turn, i) => (
                  <TurnBubble key={`${turn.round}-${turn.side}-${i}`} turn={turn} />
                ))}
              </AnimatePresence>

              {thinking && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn(
                    "flex",
                    thinking.side === "organization" ? "justify-start" : "justify-end",
                  )}
                >
                  <div
                    className={cn(
                      "rounded-xl border px-4 py-3",
                      thinking.side === "organization"
                        ? "border-org/25 bg-org/[0.06]"
                        : "border-counterparty/25 bg-counterparty/[0.06]",
                    )}
                  >
                    <ThinkingIndicator
                      label={`${thinking.role} is composing a response`}
                      tone={thinking.side === "organization" ? "org" : "counterparty"}
                    />
                  </div>
                </motion.div>
              )}
            </div>
          </Card>

          {/* outcome */}
          {outcome && (
            <OutcomeCard
              outcome={outcome}
              summary={summary}
              escalation={escalation}
              clauseId={clauseId}
            />
          )}
        </div>

        {/* ── Strategy Coach ── */}
        <div className="space-y-4">
          <Card className="lg:sticky lg:top-24" data-testid="strategy-coach">
            <div className="mb-1 flex items-center gap-2">
              <Brain className="size-3.5 text-accent" />
              <CardTitle>Strategy Coach</CardTitle>
            </div>
            <p className="mb-4 text-2xs leading-relaxed text-silver-500">
              Predicts whether the counterparty will accept, and what to do next.
            </p>

            {!latestCoaching ? (
              <p className="py-6 text-center text-2xs text-silver-500">
                Coaching appears after our first turn.
              </p>
            ) : (
              <div className="space-y-4">
                {/* acceptance probability dial */}
                <div>
                  <div className="mb-2 flex items-baseline justify-between">
                    <p className="text-2xs uppercase tracking-wider text-silver-500">
                      Acceptance probability
                    </p>
                    <p
                      className={cn(
                        "numeric text-2xl font-semibold",
                        latestCoaching.acceptance_probability >= 65
                          ? "text-risk-low"
                          : latestCoaching.acceptance_probability >= 35
                            ? "text-risk-medium"
                            : "text-risk-critical",
                      )}
                    >
                      <AnimatedNumber
                        value={latestCoaching.acceptance_probability}
                        suffix="%"
                      />
                    </p>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-base-700/70">
                    <motion.div
                      className={cn(
                        "h-full rounded-full",
                        latestCoaching.acceptance_probability >= 65
                          ? "bg-risk-low"
                          : latestCoaching.acceptance_probability >= 35
                            ? "bg-risk-medium"
                            : "bg-risk-critical",
                      )}
                      animate={{ width: `${latestCoaching.acceptance_probability}%` }}
                      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
                    />
                  </div>
                </div>

                <div className="rounded-lg border border-accent/20 bg-accent/[0.05] p-3">
                  <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-accent-soft">
                    <Lightbulb className="size-3" /> Recommended move
                  </p>
                  <p className="text-xs leading-relaxed text-silver-200">
                    {latestCoaching.recommended_move}
                  </p>
                </div>

                <div>
                  <p className="eyebrow mb-1.5">Leverage</p>
                  <p className="text-2xs leading-relaxed text-silver-400">
                    {latestCoaching.leverage_assessment}
                  </p>
                </div>

                <div>
                  <p className="eyebrow mb-1.5">Risk of pushing further</p>
                  <p className="text-2xs leading-relaxed text-silver-400">
                    {latestCoaching.risks_of_pushing}
                  </p>
                </div>

                {latestCoaching.walk_away_signal && (
                  <Alert variant="warning" title="Walk-away signal">
                    The coach assesses the gap as unlikely to close on acceptable terms.
                  </Alert>
                )}

                {/* probability history */}
                {coaching.length > 1 && (
                  <div className="border-t border-silver-50/[0.06] pt-3">
                    <p className="eyebrow mb-2">By round</p>
                    <div className="flex items-end gap-1.5">
                      {coaching.map((entry) => (
                        <div key={entry.round} className="flex flex-1 flex-col items-center gap-1">
                          <div className="flex h-16 w-full items-end">
                            <motion.div
                              className="w-full rounded-t bg-accent/50"
                              initial={{ height: 0 }}
                              animate={{ height: `${entry.acceptance_probability}%` }}
                              transition={{ duration: 0.5 }}
                            />
                          </div>
                          <span className="numeric text-[0.625rem] text-silver-600">
                            {entry.acceptance_probability}
                          </span>
                          <span className="text-[0.625rem] text-silver-600">R{entry.round}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </PageTransition>
  );
}

/* ── seat card ──────────────────────────────────────────────────────────── */

function SeatCard({
  side,
  seat,
  active,
  turnCount,
}: {
  side: NegotiationSide;
  seat?: Seat;
  active: boolean;
  turnCount: number;
}) {
  const isOrg = side === "organization";
  const Icon = isOrg ? Building2 : Scale;

  return (
    <Card
      className={cn(
        "relative overflow-hidden transition-all duration-300",
        isOrg ? "border-org/20" : "border-counterparty/20",
        active && (isOrg ? "border-org/60 shadow-glow-sm" : "border-counterparty/60"),
      )}
    >
      {active && (
        <motion.span
          className={cn(
            "absolute inset-x-0 top-0 h-0.5",
            isOrg ? "bg-org" : "bg-counterparty",
          )}
          animate={{ opacity: [0.35, 1, 0.35] }}
          transition={{ duration: 1.4, repeat: Infinity }}
        />
      )}
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid size-10 shrink-0 place-items-center rounded-lg",
            isOrg
              ? "bg-org/12 text-org ring-1 ring-org/25"
              : "bg-counterparty/12 text-counterparty ring-1 ring-counterparty/25",
          )}
        >
          <Icon className="size-4.5" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-silver-100">
            {isOrg ? "Our side" : "Counterparty"}
          </p>
          <p className="mt-0.5 truncate text-2xs text-silver-500">
            {seat?.role ?? (isOrg ? "Organization Negotiator" : "Counterparty Negotiator")}
          </p>
          <Badge variant={isOrg ? "org" : "counterparty"} size="sm" className="mt-2">
            {turnCount} turn{turnCount === 1 ? "" : "s"}
          </Badge>
        </div>
      </div>
      {seat?.persona && (
        <p className="mt-3 line-clamp-3 border-t border-silver-50/[0.06] pt-3 text-[0.625rem] italic leading-relaxed text-silver-500">
          {seat.persona}
        </p>
      )}
    </Card>
  );
}

/* ── turn bubble ────────────────────────────────────────────────────────── */

const STANCE_META: Record<string, { variant: "low" | "medium" | "high" | "critical" | "neutral"; label: string }> = {
  accept: { variant: "low", label: "accepts" },
  counter: { variant: "neutral", label: "counters" },
  reject: { variant: "critical", label: "rejects" },
  escalate: { variant: "high", label: "escalates" },
};

function TurnBubble({ turn }: { turn: NegotiationTurn }) {
  const [showLanguage, setShowLanguage] = React.useState(false);
  const isOrg = turn.side === "organization";
  const stance = STANCE_META[turn.stance] ?? STANCE_META.counter;

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className={cn("flex", isOrg ? "justify-start" : "justify-end")}
      data-testid="negotiation-turn"
    >
      <div className={cn("max-w-[88%]", isOrg ? "items-start" : "items-end")}>
        <div
          className={cn(
            "mb-1.5 flex flex-wrap items-center gap-2",
            !isOrg && "justify-end",
          )}
        >
          <span
            className={cn(
              "text-2xs font-semibold",
              isOrg ? "text-org" : "text-counterparty",
            )}
          >
            {isOrg ? "Organization Agent" : "Counterparty Agent"}
          </span>
          <Badge variant="neutral" size="sm">
            R{turn.round}
          </Badge>
          <Badge variant={stance.variant} size="sm">
            {stance.label}
          </Badge>
          <span className="numeric text-[0.625rem] text-silver-600">
            conf {formatPct(turn.confidence)}
          </span>
        </div>

        <div
          className={cn(
            "rounded-xl border px-4 py-3",
            isOrg
              ? "border-org/20 bg-org/[0.06]"
              : "border-counterparty/20 bg-counterparty/[0.06]",
          )}
        >
          <p className="text-xs leading-relaxed text-silver-200">{turn.message}</p>

          {turn.concession && turn.concession !== "none" && (
            <p className="mt-2.5 flex items-start gap-1.5 border-t border-silver-50/[0.06] pt-2.5 text-[0.625rem] leading-relaxed text-silver-400">
              <Handshake className="mt-0.5 size-2.5 shrink-0" />
              <span>
                <span className="font-semibold uppercase tracking-wider">Concession:</span>{" "}
                {turn.concession}
              </span>
            </p>
          )}

          {turn.proposed_language && (
            <>
              <button
                type="button"
                onClick={() => setShowLanguage((s) => !s)}
                className="mt-2.5 text-[0.625rem] font-semibold uppercase tracking-wider text-accent-soft underline-offset-2 hover:underline"
              >
                {showLanguage ? "Hide" : "Show"} proposed language
              </button>
              <AnimatePresence>
                {showLanguage && (
                  <motion.p
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-2 overflow-hidden whitespace-pre-wrap rounded-md border border-silver-50/[0.07] bg-base-900/60 p-2.5 font-mono text-[0.625rem] leading-relaxed text-silver-300"
                  >
                    {turn.proposed_language}
                  </motion.p>
                )}
              </AnimatePresence>
            </>
          )}
        </div>

        <p
          className={cn(
            "mt-1 text-[0.625rem] text-silver-600",
            !isOrg && "text-right",
          )}
        >
          projects risk at{" "}
          <span className="numeric font-semibold">{turn.projected_risk_score}</span>
        </p>
      </div>
    </motion.div>
  );
}

/* ── outcome ────────────────────────────────────────────────────────────── */

function OutcomeCard({
  outcome,
  summary,
  escalation,
  clauseId,
}: {
  outcome: { outcome: string; reason: string };
  summary: Record<string, unknown> | null;
  escalation: Record<string, unknown> | null;
  clauseId: string;
}) {
  const accepted = outcome.outcome === "accepted";
  const escalated = outcome.outcome === "escalated";
  const Icon = accepted ? CheckCircle2 : escalated ? Gavel : XCircle;

  return (
    <Card
      className={cn(
        accepted
          ? "border-risk-low/30"
          : escalated
            ? "border-risk-high/30"
            : "border-risk-critical/30",
      )}
      data-testid="negotiation-outcome"
    >
      <div className="flex items-start gap-3">
        <Icon
          className={cn(
            "mt-0.5 size-5 shrink-0",
            accepted ? "text-risk-low" : escalated ? "text-risk-high" : "text-risk-critical",
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>Negotiation {outcome.outcome}</CardTitle>
            {summary?.rounds_used !== undefined && (
              <Badge variant="neutral" size="sm">
                {String(summary.rounds_used)} rounds
              </Badge>
            )}
            {typeof summary?.risk_reduction === "number" && summary.risk_reduction > 0 && (
              <Badge variant="low" size="sm">
                risk −{summary.risk_reduction as number}
              </Badge>
            )}
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-silver-400">{outcome.reason}</p>

          {escalation?.should_escalate ? (
            <div className="mt-4 rounded-lg border border-risk-high/25 bg-risk-high/[0.05] p-3.5">
              <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-risk-high">
                <Gavel className="size-3" /> Escalated to human review ·{" "}
                {String(escalation.priority)} priority
              </p>
              <p className="text-xs leading-relaxed text-silver-300">
                {String(escalation.reason ?? "")}
              </p>
              {escalation.recommended_action ? (
                <p className="mt-2 text-2xs leading-relaxed text-silver-400">
                  <span className="font-semibold">Decision needed:</span>{" "}
                  {String(escalation.recommended_action)}
                </p>
              ) : null}
              <Button variant="outline" size="sm" className="mt-3" asChild>
                <Link href="/review">Open review queue →</Link>
              </Button>
            </div>
          ) : null}

          {typeof summary?.final_language === "string" && summary.final_language ? (
            <div className="mt-4">
              <p className="eyebrow mb-2">Final position</p>
              <p className="whitespace-pre-wrap rounded-lg border border-silver-50/[0.06] bg-base-900/50 p-3 font-mono text-2xs leading-relaxed text-silver-300">
                {summary.final_language as string}
              </p>
            </div>
          ) : null}

          <p className="mt-4 border-t border-silver-50/[0.06] pt-3 text-[0.625rem] leading-relaxed text-silver-600">
            The negotiated position is saved as a new clause version and still requires human
            approval before it is finalised. Review it in the{" "}
            <Link href={`/clauses/${clauseId}`} className="text-accent-soft underline underline-offset-2">
              clause workspace
            </Link>
            .
          </p>
        </div>
      </div>
    </Card>
  );
}

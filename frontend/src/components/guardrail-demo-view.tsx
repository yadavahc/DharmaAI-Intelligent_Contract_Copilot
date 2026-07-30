"use client";

import {
  Ban,
  Eraser,
  Play,
  ShieldAlert,
  ShieldCheck,
  Syringe,
  UserCheck,
  UserX,
  Wand2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { GuardrailVerdictCard } from "@/components/guardrail-verdict";
import { PageTransition, Reveal } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  SectionHeading,
  Select,
  SkeletonCard,
  Textarea,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { GuardrailVerdict } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

type GuardrailKey = "prompt_injection" | "pii_detection" | "hallucination_flag" | "approval_gate";

const TABS: { key: GuardrailKey; label: string; icon: LucideIcon }[] = [
  { key: "prompt_injection", label: "Prompt injection", icon: Syringe },
  { key: "pii_detection", label: "PII & secrets", icon: Ban },
  { key: "hallucination_flag", label: "Hallucination", icon: Wand2 },
  { key: "approval_gate", label: "Approval gate", icon: UserCheck },
];

interface Sample {
  guardrail: string;
  label: string;
  text?: string;
  source_text?: string;
  agent_output?: Record<string, unknown>;
  redline?: Record<string, unknown>;
  risk_level?: string;
}

/**
 * The guardrail demo page.
 *
 * Each tab posts live input to the backend and renders the verdict object it
 * returns, unmodified — so what is on screen is the same structure the pipeline
 * acts on, not a re-enactment. The inputs stay editable so the guardrails can be
 * shown firing on arbitrary text, not just the canned samples.
 */
export function GuardrailDemoView() {
  const [active, setActive] = React.useState<GuardrailKey>("prompt_injection");
  const [info, setInfo] = React.useState<Record<string, unknown>[] | null>(null);
  const [samples, setSamples] = React.useState<Sample[]>([]);

  const [text, setText] = React.useState("");
  const [sourceText, setSourceText] = React.useState("");
  const [agentOutput, setAgentOutput] = React.useState("");
  const [gateRole, setGateRole] = React.useState("BUSINESS_USER");
  const [gateDecision, setGateDecision] = React.useState("approve");

  const [verdicts, setVerdicts] = React.useState<GuardrailVerdict[] | null>(null);
  const [extras, setExtras] = React.useState<Record<string, unknown> | null>(null);
  const [gateResult, setGateResult] = React.useState<Awaited<
    ReturnType<typeof api.testApprovalGate>
  > | null>(null);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    api.guardrailInfo().then((r) => setInfo(r.guardrails)).catch(() => setInfo(null));
    api
      .guardrailSamples()
      .then((r) => setSamples(r.samples as unknown as Sample[]))
      .catch(() => setSamples([]));
  }, []);

  // Load the matching sample whenever the tab changes, so each tab arrives ready
  // to run rather than requiring the presenter to invent an attack string.
  React.useEffect(() => {
    const sample = samples.find((s) => s.guardrail === active);
    setVerdicts(null);
    setExtras(null);
    setGateResult(null);
    setError(null);
    if (!sample) return;
    setText(sample.text ?? "");
    setSourceText(sample.source_text ?? "");
    setAgentOutput(sample.agent_output ? JSON.stringify(sample.agent_output, null, 2) : "");
  }, [active, samples]);

  const activeSample = samples.find((s) => s.guardrail === active);

  const run = async () => {
    setRunning(true);
    setError(null);
    setVerdicts(null);
    setExtras(null);
    setGateResult(null);

    try {
      if (active === "approval_gate") {
        const result = await api.testApprovalGate({
          redline: activeSample?.redline ?? {
            original: "Customer shall have unlimited liability.",
            suggested: "Each party's aggregate liability shall not exceed 12 months of fees.",
            reason: "Removes uncapped exposure.",
            materiality: "high",
            confidence: 0.62,
          },
          risk_level: activeSample?.risk_level ?? "Critical",
          attempt: {
            current_state: "pending_human_approval",
            decision: gateDecision,
            actor_role: gateRole,
            actor_id: `demo-${gateRole.toLowerCase()}`,
            edited_text:
              gateDecision === "edit"
                ? "Each party's aggregate liability shall not exceed 15 months of fees."
                : undefined,
          },
        });
        setGateResult(result);
        setVerdicts([result.verdict]);
        if (result.attempt_allowed === false) {
          toast.error("Gate refused the action", { description: result.attempt_error });
        } else if (result.attempt_allowed) {
          toast.success("Gate allowed the action");
        }
      } else if (active === "hallucination_flag") {
        let parsed: Record<string, unknown>;
        try {
          parsed = JSON.parse(agentOutput);
        } catch {
          setError("Agent output must be valid JSON.");
          setRunning(false);
          return;
        }
        const result = await api.testGuardrail({
          guardrail: "hallucination",
          agent_output: parsed,
          source_text: sourceText,
        });
        setVerdicts(result.verdicts);
      } else {
        const result = await api.testGuardrail({
          guardrail: active === "pii_detection" ? "pii" : "prompt_injection",
          text,
        });
        setVerdicts(result.verdicts);
        setExtras({
          sanitized_text: result.sanitized_text,
          sanitized_spans: result.sanitized_spans,
          redacted_text: result.redacted_text,
          redacted_items: result.redacted_items,
        });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  const activeInfo = info?.find((g) => g.key === active) as
    | { name: string; runs_on: string; why: string; action: string }
    | undefined;

  return (
    <PageTransition>
      <SectionHeading
        eyebrow="Safety"
        title="Guardrail demo"
        description="Four guardrails, each running live against the input below. The verdicts shown are the exact objects the pipeline acts on."
      />

      {/* ── tabs ── */}
      <div className="mb-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = active === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActive(tab.key)}
              className={cn(
                "flex items-center gap-2.5 rounded-xl border px-3.5 py-3 text-left transition-all duration-200 ease-premium",
                isActive
                  ? "border-accent/45 bg-accent/[0.07] shadow-glow-sm"
                  : "border-silver-50/[0.07] bg-base-800/40 hover:border-silver-50/15",
              )}
              aria-pressed={isActive}
              data-testid={`guardrail-tab-${tab.key}`}
            >
              <Icon className={cn("size-4 shrink-0", isActive ? "text-accent" : "text-silver-400")} />
              <span
                className={cn(
                  "text-xs font-semibold",
                  isActive ? "text-silver-50" : "text-silver-300",
                )}
              >
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* ── what this guardrail does ── */}
      {activeInfo && (
        <Card className="mb-5 border-accent/15 bg-accent/[0.03]">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" />
            <div className="min-w-0">
              <CardTitle>{activeInfo.name}</CardTitle>
              <dl className="mt-2.5 space-y-1.5 text-2xs leading-relaxed">
                <div>
                  <dt className="inline font-semibold uppercase tracking-wider text-silver-500">
                    Runs on:{" "}
                  </dt>
                  <dd className="inline text-silver-300">{activeInfo.runs_on}</dd>
                </div>
                <div>
                  <dt className="inline font-semibold uppercase tracking-wider text-silver-500">
                    Why:{" "}
                  </dt>
                  <dd className="inline text-silver-300">{activeInfo.why}</dd>
                </div>
                <div>
                  <dt className="inline font-semibold uppercase tracking-wider text-silver-500">
                    Action:{" "}
                  </dt>
                  <dd className="inline text-silver-300">{activeInfo.action}</dd>
                </div>
              </dl>
            </div>
          </div>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        {/* ── input ── */}
        <Card>
          <div className="mb-3 flex items-center justify-between gap-3">
            <CardTitle>Live input</CardTitle>
            {activeSample && (
              <Badge variant="neutral" size="sm">
                {activeSample.label}
              </Badge>
            )}
          </div>

          {active === "approval_gate" ? (
            <div className="space-y-4">
              <Alert variant="info" title="This gate is enforced in code">
                Pick a role and a decision, then run it. The backend&apos;s{" "}
                <code className="font-mono">apply_gate</code> function raises for unauthorised roles
                and invalid state transitions — the refusal you see is real, not simulated.
              </Alert>

              <div className="rounded-lg border border-silver-50/[0.06] bg-base-900/50 p-3">
                <p className="mb-1.5 text-[0.625rem] uppercase tracking-wider text-silver-500">
                  Redline awaiting approval
                </p>
                <p className="font-mono text-2xs leading-relaxed text-silver-400 line-through decoration-risk-critical/50">
                  {String(activeSample?.redline?.original ?? "Customer shall have unlimited liability.")}
                </p>
                <p className="mt-2 font-mono text-2xs leading-relaxed text-risk-low">
                  {String(
                    activeSample?.redline?.suggested ??
                      "Each party's aggregate liability shall not exceed 12 months of fees.",
                  )}
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="gate-role"
                    className="mb-1.5 block text-xs font-medium text-silver-300"
                  >
                    Acting role
                  </label>
                  <Select
                    id="gate-role"
                    value={gateRole}
                    onChange={(e) => setGateRole(e.target.value)}
                  >
                    <option value="BUSINESS_USER">Business User (not authorised)</option>
                    <option value="REVIEWER">Reviewer</option>
                    <option value="ADMIN">Admin</option>
                  </Select>
                </div>
                <div>
                  <label
                    htmlFor="gate-decision"
                    className="mb-1.5 block text-xs font-medium text-silver-300"
                  >
                    Decision
                  </label>
                  <Select
                    id="gate-decision"
                    value={gateDecision}
                    onChange={(e) => setGateDecision(e.target.value)}
                  >
                    <option value="approve">Approve</option>
                    <option value="edit">Edit and approve</option>
                    <option value="reject">Reject</option>
                    <option value="comment">Comment only</option>
                    <option value="publish">publish (invalid decision)</option>
                  </Select>
                </div>
              </div>
            </div>
          ) : active === "hallucination_flag" ? (
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="source-text"
                  className="mb-1.5 block text-xs font-medium text-silver-300"
                >
                  Source clause (ground truth)
                </label>
                <Textarea
                  id="source-text"
                  value={sourceText}
                  onChange={(e) => setSourceText(e.target.value)}
                  rows={3}
                  className="font-mono text-xs"
                />
              </div>
              <div>
                <label
                  htmlFor="agent-output"
                  className="mb-1.5 block text-xs font-medium text-silver-300"
                >
                  Agent output (JSON)
                </label>
                <Textarea
                  id="agent-output"
                  value={agentOutput}
                  onChange={(e) => setAgentOutput(e.target.value)}
                  rows={10}
                  className="font-mono text-xs"
                />
                <p className="mt-1.5 text-[0.625rem] leading-relaxed text-silver-600">
                  The sample asserts a &ldquo;$50,000 cap&rdquo; that does not appear in the source
                  clause, and reports 0.41 confidence. Both are caught.
                </p>
              </div>
            </div>
          ) : (
            <div>
              <Textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={12}
                className="font-mono text-xs"
                placeholder="Paste contract text to scan…"
                data-testid="guardrail-input"
              />
              <p className="mt-1.5 text-[0.625rem] leading-relaxed text-silver-600">
                Editable — try your own wording to see what does and does not trip the detector.
              </p>
            </div>
          )}

          <Button
            variant="primary"
            className="mt-4 w-full"
            onClick={run}
            loading={running}
            data-testid="run-guardrail"
          >
            <Play className="size-4" /> Run {titleCase(active)}
          </Button>
        </Card>

        {/* ── verdict ── */}
        <div className="space-y-4">
          {error && (
            <Alert variant="danger" icon={<ShieldAlert className="size-3.5" />}>
              {error}
            </Alert>
          )}

          {running ? (
            <SkeletonCard lines={6} />
          ) : verdicts === null ? (
            <Card className="flex min-h-56 items-center justify-center border-dashed">
              <p className="max-w-xs text-center text-xs leading-relaxed text-silver-500">
                Run the guardrail to see the verdict — including every matched rule and the exact
                excerpt that triggered it.
              </p>
            </Card>
          ) : (
            <Reveal className="space-y-4">
              {verdicts.map((verdict, i) => (
                <GuardrailVerdictCard
                  key={`${verdict.guardrail}-${i}`}
                  verdict={verdict}
                  defaultOpen
                />
              ))}

              {/* gate attempt result */}
              {gateResult && gateResult.attempt_allowed !== undefined && (
                <Card
                  className={cn(
                    gateResult.attempt_allowed ? "border-risk-low/30" : "border-risk-critical/30",
                  )}
                  data-testid="gate-attempt-result"
                >
                  <div className="flex items-start gap-3">
                    {gateResult.attempt_allowed ? (
                      <UserCheck className="mt-0.5 size-4 shrink-0 text-risk-low" />
                    ) : (
                      <UserX className="mt-0.5 size-4 shrink-0 text-risk-critical" />
                    )}
                    <div className="min-w-0">
                      <CardTitle>
                        {gateResult.attempt_allowed
                          ? `Action allowed for ${gateRole}`
                          : `Action refused for ${gateRole}`}
                      </CardTitle>
                      {gateResult.attempt_error ? (
                        <p className="mt-1.5 font-mono text-2xs leading-relaxed text-risk-critical">
                          {gateResult.attempt_error}
                        </p>
                      ) : (
                        <dl className="mt-2 space-y-1">
                          {Object.entries(gateResult.attempt_result ?? {}).map(([key, value]) => (
                            <div key={key} className="flex gap-2 text-2xs">
                              <dt className="text-silver-500">{titleCase(key)}:</dt>
                              <dd className="font-mono text-silver-300">
                                {value === null ? "—" : String(value)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      )}
                    </div>
                  </div>
                </Card>
              )}

              {/* sanitised / redacted output */}
              {extras?.sanitized_text ? (
                <Card>
                  <div className="mb-2 flex items-center gap-2">
                    <Eraser className="size-3.5 text-risk-high" />
                    <CardTitle>
                      Neutralised text ({String(extras.sanitized_spans)} span
                      {extras.sanitized_spans === 1 ? "" : "s"})
                    </CardTitle>
                  </div>
                  <p className="mb-2 text-2xs leading-relaxed text-silver-500">
                    Injected instructions are wrapped rather than deleted, so the clause stays
                    reviewable while the agents read them as inert quoted text.
                  </p>
                  <p className="max-h-56 overflow-auto whitespace-pre-wrap rounded-md border border-silver-50/[0.06] bg-base-900/60 p-3 font-mono text-2xs leading-relaxed text-silver-300">
                    {String(extras.sanitized_text)}
                  </p>
                </Card>
              ) : null}

              {extras?.redacted_text ? (
                <Card>
                  <div className="mb-2 flex items-center gap-2">
                    <Ban className="size-3.5 text-risk-critical" />
                    <CardTitle>
                      Redacted text ({String(extras.redacted_items)} item
                      {extras.redacted_items === 1 ? "" : "s"})
                    </CardTitle>
                  </div>
                  <p className="max-h-56 overflow-auto whitespace-pre-wrap rounded-md border border-silver-50/[0.06] bg-base-900/60 p-3 font-mono text-2xs leading-relaxed text-silver-300">
                    {String(extras.redacted_text)}
                  </p>
                </Card>
              ) : null}
            </Reveal>
          )}
        </div>
      </div>
    </PageTransition>
  );
}

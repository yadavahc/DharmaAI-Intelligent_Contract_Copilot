"use client";

import Editor from "@monaco-editor/react";
import {
  FlaskConical,
  Minus,
  RotateCcw,
  TrendingDown,
  TrendingUp,
  Wand2,
} from "lucide-react";
import * as React from "react";

import { AnimatedNumber, motion } from "@/components/ui/motion";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  Skeleton,
  Spinner,
  Tooltip,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { SimulationResult } from "@/lib/types";
import { cn, riskClasses } from "@/lib/utils";

/**
 * Feature 2 — Clause Risk Simulator.
 *
 * Edit the clause in a Monaco editor; the clause score *and* the whole-contract
 * score recompute live, with the delta shown inline.
 *
 * Two deliberate choices:
 *
 *  * **Debounced, not per-keystroke.** 450 ms after typing stops. Firing on every
 *    keystroke would queue dozens of redundant requests and make the numbers
 *    flicker; waiting for a blur would not feel live.
 *  * **Backed by the deterministic scorer.** `/api/clauses/simulate/contract/...`
 *    uses the same pure risk engine the pipeline uses, so it is instant, free and
 *    stable — identical text always yields an identical score. An LLM call per
 *    edit would be slow, costly, and would jitter on unchanged input.
 */

const DEBOUNCE_MS = 450;

export function RiskSimulator({
  contractId,
  clauseId,
  initialText,
  category,
  baselineScore,
}: {
  contractId: string;
  clauseId: string;
  initialText: string;
  category: string;
  baselineScore: number;
}) {
  const [text, setText] = React.useState(initialText);
  const [result, setResult] = React.useState<SimulationResult | null>(null);
  const [simulating, setSimulating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [editorReady, setEditorReady] = React.useState(false);

  const requestId = React.useRef(0);
  const dirty = text.trim() !== initialText.trim();

  React.useEffect(() => {
    if (!dirty) {
      setResult(null);
      setError(null);
      return;
    }

    const handle = setTimeout(async () => {
      // Guard against out-of-order responses: only the newest request may write.
      const id = ++requestId.current;
      setSimulating(true);
      try {
        const response = await api.simulateContract(contractId, clauseId, text);
        if (id === requestId.current) {
          setResult(response);
          setError(null);
        }
      } catch (err) {
        if (id === requestId.current) setError(String(err));
      } finally {
        if (id === requestId.current) setSimulating(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(handle);
  }, [text, dirty, contractId, clauseId]);

  const clauseDelta = result?.clause.delta ?? 0;
  const contractDelta = result?.contract.delta ?? 0;

  return (
    <Card data-testid="risk-simulator">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <FlaskConical className="size-3.5 text-accent" />
        <CardTitle>Clause Risk Simulator</CardTitle>
        {dirty && (
          <Badge variant="medium" size="sm">
            unsaved draft
          </Badge>
        )}
        {dirty && (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => setText(initialText)}
          >
            <RotateCcw className="size-3" /> Reset
          </Button>
        )}
      </div>
      <p className="mb-4 text-2xs leading-relaxed text-silver-500">
        Edit the clause and watch the risk score move. Scoring is deterministic — the same
        wording always produces the same number — so this is a real what-if, not a guess.
      </p>

      {/* ── editor ── */}
      <div className="relative overflow-hidden rounded-lg border border-silver-50/[0.08]">
        {!editorReady && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-base-900">
            <div className="flex items-center gap-2 text-2xs text-silver-500">
              <Spinner className="size-3.5" /> Loading editor…
            </div>
          </div>
        )}
        <Editor
          height="240px"
          defaultLanguage="plaintext"
          value={text}
          onChange={(value) => setText(value ?? "")}
          onMount={() => setEditorReady(true)}
          loading={<div className="h-[240px] bg-base-900" />}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 12,
            lineHeight: 20,
            fontFamily: "var(--font-mono), monospace",
            wordWrap: "on",
            wrappingIndent: "same",
            lineNumbers: "on",
            lineNumbersMinChars: 3,
            scrollBeyondLastLine: false,
            renderLineHighlight: "none",
            padding: { top: 12, bottom: 12 },
            overviewRulerLanes: 0,
            hideCursorInOverviewRuler: true,
            scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
            // Code affordances are noise for prose; turn them off.
            quickSuggestions: false,
            suggestOnTriggerCharacters: false,
            occurrencesHighlight: "off",
            folding: false,
            matchBrackets: "never",
            contextmenu: false,
          }}
        />
      </div>

      {/* ── live results ── */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <ScorePanel
          label="This clause"
          before={result?.clause.before.score ?? baselineScore}
          after={result?.clause.after.score ?? baselineScore}
          level={result?.clause.after.level ?? undefined}
          delta={clauseDelta}
          active={dirty}
          simulating={simulating}
        />
        <ScorePanel
          label="Whole contract"
          before={result?.contract.before.score ?? 0}
          after={result?.contract.after.score ?? 0}
          level={result?.contract.after.level ?? undefined}
          delta={contractDelta}
          active={dirty && !!result}
          simulating={simulating}
        />
      </div>

      {error && (
        <p className="mt-3 text-2xs text-risk-critical">
          Simulation failed: {error}
        </p>
      )}

      {/* ── what changed ── */}
      {result && (
        <div className="mt-4 space-y-3 border-t border-silver-50/[0.06] pt-4">
          <div>
            <p className="eyebrow mb-1.5">Why</p>
            <p className="text-2xs leading-relaxed text-silver-400">{result.clause.rationale}</p>
          </div>

          {result.clause.findings.length > 0 && (
            <div>
              <p className="eyebrow mb-2">Signals detected in your draft</p>
              <div className="flex flex-wrap gap-1.5">
                {result.clause.findings.map((finding, i) => (
                  <Tooltip
                    key={`${finding.code}-${i}`}
                    content={`${finding.source} · ${finding.points > 0 ? "+" : ""}${finding.points} points`}
                  >
                    <span
                      className={cn(
                        "flex items-center gap-1.5 rounded-md border px-2 py-1 text-[0.625rem]",
                        finding.points > 0
                          ? "border-risk-high/25 bg-risk-high/[0.08] text-risk-high"
                          : "border-risk-low/25 bg-risk-low/[0.08] text-risk-low",
                      )}
                    >
                      {finding.points > 0 ? (
                        <TrendingUp className="size-2.5" />
                      ) : (
                        <TrendingDown className="size-2.5" />
                      )}
                      {finding.detail}
                    </span>
                  </Tooltip>
                ))}
              </div>
            </div>
          )}

          <p className="text-[0.625rem] leading-relaxed text-silver-600">
            This is a simulation only — nothing is saved. To make a change stick, propose it as a
            redline and take it through the approval gate.
          </p>
        </div>
      )}

      {!dirty && (
        <p className="mt-4 flex items-center gap-1.5 text-2xs text-silver-600">
          <Wand2 className="size-3" />
          Start editing above to see the score move.
        </p>
      )}
    </Card>
  );
}

function ScorePanel({
  label,
  before,
  after,
  level,
  delta,
  active,
  simulating,
}: {
  label: string;
  before: number;
  after: number;
  level?: string;
  delta: number;
  active: boolean;
  simulating: boolean;
}) {
  const improved = delta < -0.05;
  const worsened = delta > 0.05;
  const risk = riskClasses(level);

  return (
    <div className="rounded-lg border border-silver-50/[0.07] bg-base-900/40 p-3.5">
      <div className="flex items-center justify-between">
        <p className="text-2xs uppercase tracking-wider text-silver-500">{label}</p>
        {simulating && <Spinner className="size-3 text-silver-500" />}
      </div>

      <div className="mt-2 flex items-baseline gap-2">
        <p
          className={cn(
            "numeric text-2xl font-semibold transition-colors duration-300",
            active ? risk.text : "text-silver-300",
          )}
        >
          <AnimatedNumber value={active ? after : before} decimals={1} />
        </p>

        {active && (improved || worsened) && (
          <motion.span
            key={delta}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(
              "numeric flex items-center gap-0.5 text-xs font-semibold",
              improved ? "text-risk-low" : "text-risk-critical",
            )}
          >
            {improved ? (
              <TrendingDown className="size-3" />
            ) : (
              <TrendingUp className="size-3" />
            )}
            {delta > 0 ? "+" : ""}
            {delta.toFixed(1)}
          </motion.span>
        )}
        {active && !improved && !worsened && (
          <span className="flex items-center gap-0.5 text-xs text-silver-500">
            <Minus className="size-3" /> no change
          </span>
        )}
      </div>

      {active && (
        <p className="mt-1.5 text-[0.625rem] text-silver-600">
          was <span className="numeric">{before.toFixed(1)}</span>
          {level && ` · now ${level}`}
        </p>
      )}
    </div>
  );
}

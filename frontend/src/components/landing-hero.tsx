"use client";

import { ArrowRight, CheckCircle2, CircleDot, Loader2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { AnimatedNumber, Reveal, motion } from "@/components/ui/motion";
import { Badge, Button, Card } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { LyzrRuntime } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Landing hero with a self-running preview of the agent pipeline.
 *
 * The preview loops through the pipeline stages so the page demonstrates the
 * product rather than describing it. It is illustrative and labelled as such —
 * real numbers live in the app itself.
 */

const STAGES = [
  { agent: "Contract Parsing", detail: "17 clauses identified · parties extracted", risk: 0 },
  { agent: "Clause Classification", detail: "Liability · confidence 0.94", risk: 42 },
  { agent: "Playbook Validation", detail: "PB-LIAB-002 breached · uncapped liability", risk: 68 },
  { agent: "Risk Assessment", detail: "100/100 Critical · unlimited exposure", risk: 100 },
  { agent: "Redline", detail: "Cap proposed at 12 months of fees", risk: 74 },
  { agent: "Negotiation ×2", detail: "4 rounds · settled at 15 months", risk: 46 },
  { agent: "Escalation", detail: "Routed to Reviewer · high priority", risk: 46 },
];

export function LandingHero() {
  const [active, setActive] = React.useState(0);

  React.useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setActive(STAGES.length - 1);
      return;
    }
    const interval = setInterval(() => {
      setActive((current) => (current + 1) % STAGES.length);
    }, 2100);
    return () => clearInterval(interval);
  }, []);

  const stage = STAGES[active];

  return (
    <section className="container relative pt-16 sm:pt-24 lg:pt-28">
      <div className="grid gap-14 lg:grid-cols-[1.05fr_1fr] lg:items-center">
        {/* ── copy ── */}
        <div>
          <Reveal>
            <Badge variant="accent" className="mb-6">
              <CircleDot className="size-3" />
              Legal track · multi-agent
            </Badge>
          </Reveal>

          <Reveal delay={0.05}>
            <h1 className="text-balance text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
              <span className="heading-gradient">Contract review that</span>{" "}
              <span className="text-accent">argues back</span>
            </h1>
          </Reveal>

          <Reveal delay={0.12}>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-silver-400">
              Dharma AI reads a contract, scores every clause against your playbook, drafts the
              redlines — then runs a live negotiation between two opposing agents and escalates
              what a human actually needs to decide.
            </p>
          </Reveal>

          <Reveal delay={0.18}>
            <div className="mt-9 flex flex-wrap gap-3">
              <Button variant="primary" size="lg" asChild>
                <Link href="/signin">
                  Start reviewing <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button variant="secondary" size="lg" asChild>
                <Link href="#agents">See the nine agents</Link>
              </Button>
            </div>
          </Reveal>

          <Reveal delay={0.24}>
            <dl className="mt-12 grid max-w-lg grid-cols-3 gap-6">
              {[
                { label: "Lyzr agents", value: 11, suffix: "" },
                { label: "Qdrant retrieval roles", value: 5, suffix: "" },
                { label: "Guardrails enforced", value: 4, suffix: "" },
              ].map((stat) => (
                <div key={stat.label}>
                  <dd className="numeric text-3xl font-semibold text-silver-50">
                    <AnimatedNumber value={stat.value} suffix={stat.suffix} />
                  </dd>
                  <dt className="mt-1 text-2xs uppercase tracking-wider text-silver-500">
                    {stat.label}
                  </dt>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>

        {/* ── live pipeline preview ── */}
        <Reveal delay={0.2}>
          <Card className="relative overflow-hidden p-0" flush>
            <div className="flex items-center justify-between border-b border-silver-50/[0.06] px-5 py-3.5">
              <div className="flex items-center gap-2">
                <span className="flex gap-1.5">
                  <span className="size-2.5 rounded-full bg-risk-critical/60" />
                  <span className="size-2.5 rounded-full bg-risk-medium/60" />
                  <span className="size-2.5 rounded-full bg-risk-low/60" />
                </span>
                <span className="ml-2 font-mono text-2xs text-silver-500">
                  acme-vendor-msa.pdf
                </span>
              </div>
              <Badge variant="neutral" size="sm">
                illustrative
              </Badge>
            </div>

            {/* risk gauge */}
            <div className="border-b border-silver-50/[0.06] px-5 py-4">
              <div className="flex items-baseline justify-between">
                <span className="eyebrow">Clause risk</span>
                <span
                  className={cn(
                    "numeric text-2xl font-semibold transition-colors duration-500",
                    stage.risk >= 90
                      ? "text-risk-critical"
                      : stage.risk >= 70
                        ? "text-risk-high"
                        : stage.risk >= 40
                          ? "text-risk-medium"
                          : "text-risk-low",
                  )}
                >
                  <AnimatedNumber value={stage.risk} />
                  <span className="text-sm text-silver-500">/100</span>
                </span>
              </div>
              <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-base-700/70">
                <motion.div
                  className={cn(
                    "h-full rounded-full",
                    stage.risk >= 90
                      ? "bg-risk-critical"
                      : stage.risk >= 70
                        ? "bg-risk-high"
                        : stage.risk >= 40
                          ? "bg-risk-medium"
                          : "bg-risk-low",
                  )}
                  animate={{ width: `${stage.risk}%` }}
                  transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
            </div>

            {/* agent stages */}
            <ul className="divide-y divide-silver-50/[0.04]">
              {STAGES.map((item, index) => {
                const done = index < active;
                const running = index === active;
                return (
                  <li
                    key={item.agent}
                    className={cn(
                      "flex items-center gap-3 px-5 py-3 transition-colors duration-300",
                      running && "bg-accent/[0.05]",
                    )}
                  >
                    <span className="shrink-0">
                      {done ? (
                        <CheckCircle2 className="size-4 text-accent" />
                      ) : running ? (
                        <Loader2 className="size-4 animate-spin text-accent" />
                      ) : (
                        <span className="block size-4 rounded-full border border-silver-50/12" />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p
                        className={cn(
                          "truncate text-xs font-medium transition-colors",
                          running ? "text-silver-50" : done ? "text-silver-300" : "text-silver-600",
                        )}
                      >
                        {item.agent} Agent
                      </p>
                      {(running || done) && (
                        <p className="truncate text-2xs text-silver-500">{item.detail}</p>
                      )}
                    </div>
                    {running && (
                      <motion.span
                        layoutId="hero-stage"
                        className="h-4 w-0.5 shrink-0 rounded-full bg-accent"
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>
        </Reveal>
      </div>
    </section>
  );
}

/**
 * Reports which Lyzr runtime the live backend is using.
 *
 * Reads from the API rather than hardcoding a claim, so the badge is evidence
 * rather than marketing — and it degrades to a neutral state when the backend
 * isn't running.
 */
export function LyzrRuntimeBadge() {
  const [runtime, setRuntime] = React.useState<LyzrRuntime | null>(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    api
      .lyzrRuntime()
      .then(setRuntime)
      .catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <Badge variant="neutral">
        <span className="size-1.5 rounded-full bg-silver-500" />
        Backend offline — start it to verify the runtime
      </Badge>
    );
  }

  if (!runtime) {
    return (
      <Badge variant="neutral">
        <Loader2 className="size-3 animate-spin" />
        Checking runtime…
      </Badge>
    );
  }

  return (
    <Badge variant={runtime.is_genuine_sdk ? "accent" : "medium"}>
      <span className="size-1.5 rounded-full bg-current" />
      {runtime.is_genuine_sdk
        ? `lyzr-automata v${runtime.lyzr_version} live`
        : "Lyzr compatibility shim active"}
    </Badge>
  );
}

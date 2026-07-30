import {
  ArrowRight,
  BadgeCheck,
  BookOpen,
  Boxes,
  Brain,
  Database,
  Eye,
  FileSearch,
  GitCompare,
  Layers,
  LineChart,
  Lock,
  Scale,
  ShieldCheck,
  Sparkles,
  Swords,
  Wand2,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { AmbientBackground } from "@/components/ambient-background";
import { LandingHero, LyzrRuntimeBadge } from "@/components/landing-hero";
import { Logo } from "@/components/app-shell";
import { Badge, Button, Card } from "@/components/ui/primitives";
import { Reveal } from "@/components/ui/motion";

export const metadata: Metadata = {
  title: "Dharma AI — Autonomous Contract Review & Negotiation",
};

const AGENTS = [
  { name: "Contract Parsing", icon: FileSearch, blurb: "Pulls parties, dates, governing law and document type from the four corners of the text." },
  { name: "Clause Classification", icon: Layers, blurb: "Tags every clause by operative effect — not by heading — with calibrated confidence." },
  { name: "Playbook Validation", icon: BookOpen, blurb: "Applies your written rules literally, citing the rule id it relied on." },
  { name: "Risk Assessment", icon: LineChart, blurb: "Scores 0–100 against the playbook with the specific mechanism of harm." },
  { name: "Redline", icon: GitCompare, blurb: "Redrafts in the document's own register — the minimum change that removes the risk." },
  { name: "Organization", icon: Scale, blurb: "Negotiates on your behalf: protects the downside, concedes cheap points to close." },
  { name: "Counterparty", icon: Swords, blurb: "A realistic adversary defending their standard terms with genuine authority limits." },
  { name: "Escalation", icon: BadgeCheck, blurb: "Routes high-risk or deadlocked clauses to a named human reviewer." },
  { name: "Audit", icon: Lock, blurb: "Hash-chained record of every AI decision and human action, timestamped." },
];

const FEATURES = [
  {
    icon: Eye,
    title: "Live Agent Theater",
    body:
      "Two agents negotiate as opposing seats on screen — messages streaming in real time, a round counter, and a risk gauge that moves as terms change. The multi-agent loop is visible, not buried in logs.",
  },
  {
    icon: Wand2,
    title: "Clause Risk Simulator",
    body:
      "Edit any clause in a Monaco editor and watch the whole contract's risk score recompute live, with the before/after delta inline. Deterministic, so it responds on every keystroke.",
  },
  {
    icon: Brain,
    title: "Negotiation Strategy Coach",
    body:
      "For each proposed redline an agent predicts acceptance probability 0–100% and recommends the single strongest next move, grounded in how similar disputes actually settled.",
  },
  {
    icon: Database,
    title: "Precedent Recall",
    body:
      "Qdrant search over previously approved contracts surfaces the closest accepted wording as recommended language, with a similarity score. Approved clauses feed back in as new precedent.",
  },
  {
    icon: Sparkles,
    title: "Executive AI Summary",
    body:
      "One click produces a one-page plain-English brief: obligations, financial exposure, deadlines, renewal terms, top risks and recommended actions. Exportable to PDF.",
  },
];

const GUARDRAILS = [
  { title: "Prompt-injection detection", body: "Twelve signatures plus zero-width character detection, run on document text before any agent reads it." },
  { title: "PII & secret detection", body: "Checksum-validated (Luhn) so reference numbers don't false-positive. Values are redacted before leaving the backend." },
  { title: "Hallucination flag", body: "Verifies quoted language and figures actually appear in the source clause, and thresholds self-reported confidence." },
  { title: "Human-approval gate", body: "No redline is finalised without a named human decision. Enforced in code, not just in the UI." },
];

export default function LandingPage() {
  return (
    <div className="relative min-h-dvh overflow-hidden">
      <AmbientBackground variant="auto" intensity={1} />

      {/* ── nav ── */}
      <header className="sticky top-0 z-40 border-b border-silver-50/[0.05] bg-base-950/60 backdrop-blur-xl">
        <div className="container flex h-16 items-center justify-between">
          <Logo />
          <nav className="flex items-center gap-2 sm:gap-3">
            <Button variant="ghost" size="sm" asChild className="hidden sm:inline-flex">
              <Link href="#agents">Agents</Link>
            </Button>
            <Button variant="ghost" size="sm" asChild className="hidden sm:inline-flex">
              <Link href="#features">Features</Link>
            </Button>
            <Button variant="primary" size="sm" asChild>
              <Link href="/signin">
                Open app <ArrowRight className="size-3.5" />
              </Link>
            </Button>
          </nav>
        </div>
      </header>

      {/* ── hero ── */}
      <LandingHero />

      {/* ── the pipeline ── */}
      <section className="container py-20 sm:py-28" id="pipeline">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="eyebrow mb-3">The pipeline</p>
          <h2 className="text-3xl font-semibold tracking-tight text-silver-50 sm:text-4xl">
            Upload a contract. Get a defensible position.
          </h2>
          <p className="mt-4 text-base leading-relaxed text-silver-400">
            Every step is an agent with its own role and system prompt, orchestrated through a
            Lyzr pipeline. Each hands typed results to the next.
          </p>
        </Reveal>

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { step: "01", title: "Extract & split", body: "PDF/DOCX → text → clauses, anchored on the contract's own numbering. Guardrails screen the text before any agent sees it." },
            { step: "02", title: "Classify & retrieve", body: "Each clause is categorised, then Qdrant retrieves the playbook rules and comparable clauses that actually apply to it." },
            { step: "03", title: "Score & redline", body: "Risk 0–100 blending model judgement with deterministic policy arithmetic, then a targeted redraft shown as a diff." },
            { step: "04", title: "Negotiate & escalate", body: "Two agents trade positions for N rounds. High-risk or deadlocked clauses route to a human queue." },
          ].map((item, i) => (
            <Reveal key={item.step} delay={i * 0.08}>
              <Card hover className="h-full">
                <span className="numeric text-2xs font-bold text-accent/70">{item.step}</span>
                <h3 className="mt-3 text-sm font-semibold text-silver-100">{item.title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-silver-400">{item.body}</p>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── agents ── */}
      <section className="border-y border-silver-50/[0.05] bg-base-900/25 py-20 sm:py-28" id="agents">
        <div className="container">
          <Reveal className="mx-auto max-w-2xl text-center">
            <p className="eyebrow mb-3">Nine specialised agents</p>
            <h2 className="text-3xl font-semibold tracking-tight text-silver-50 sm:text-4xl">
              Defined and orchestrated with Lyzr
            </h2>
            <p className="mt-4 text-base leading-relaxed text-silver-400">
              Each agent is a real <code className="rounded bg-base-800 px-1.5 py-0.5 font-mono text-xs text-accent-soft">lyzr_automata.Agent</code>{" "}
              with its own role and persona, emitting{" "}
              <code className="rounded bg-base-800 px-1.5 py-0.5 font-mono text-xs text-accent-soft">Task</code>{" "}
              objects that run inside a{" "}
              <code className="rounded bg-base-800 px-1.5 py-0.5 font-mono text-xs text-accent-soft">LinearSyncPipeline</code>.
            </p>
            <div className="mt-6 flex justify-center">
              <LyzrRuntimeBadge />
            </div>
          </Reveal>

          <div className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {AGENTS.map((agent, i) => {
              const Icon = agent.icon;
              return (
                <Reveal key={agent.name} delay={i * 0.05}>
                  <Card hover className="h-full">
                    <div className="flex items-start gap-3">
                      <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-accent/20 bg-accent/[0.08] text-accent-soft">
                        <Icon className="size-4" />
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-silver-100">
                          {agent.name} <span className="font-normal text-silver-500">Agent</span>
                        </h3>
                        <p className="mt-1.5 text-xs leading-relaxed text-silver-400">
                          {agent.blurb}
                        </p>
                      </div>
                    </div>
                  </Card>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── five features ── */}
      <section className="container py-20 sm:py-28" id="features">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="eyebrow mb-3">What makes it different</p>
          <h2 className="text-3xl font-semibold tracking-tight text-silver-50 sm:text-4xl">
            Five things you won&apos;t find in a clause tagger
          </h2>
        </Reveal>

        <div className="mt-14 grid gap-4 lg:grid-cols-2">
          {FEATURES.map((feature, i) => {
            const Icon = feature.icon;
            const wide = i === 0;
            return (
              <Reveal key={feature.title} delay={i * 0.07} className={wide ? "lg:col-span-2" : ""}>
                <Card hover className="h-full">
                  <div className="flex items-start gap-4">
                    <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-accent/25 to-accent/5 text-accent-soft ring-1 ring-accent/20">
                      <Icon className="size-5" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-semibold text-silver-50">{feature.title}</h3>
                        <Badge variant="accent" size="sm">
                          {String(i + 1).padStart(2, "0")}
                        </Badge>
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-silver-400">{feature.body}</p>
                    </div>
                  </div>
                </Card>
              </Reveal>
            );
          })}
        </div>
      </section>

      {/* ── qdrant ── */}
      <section className="border-y border-silver-50/[0.05] bg-base-900/25 py-20 sm:py-28">
        <div className="container grid gap-12 lg:grid-cols-2 lg:items-center">
          <Reveal>
            <p className="eyebrow mb-3">Vector retrieval, not vector storage</p>
            <h2 className="text-3xl font-semibold tracking-tight text-silver-50 sm:text-4xl">
              Qdrant does five jobs here
            </h2>
            <p className="mt-4 text-base leading-relaxed text-silver-400">
              Four collections, each queried with different filters and thresholds — because
              &ldquo;embed the documents&rdquo; is not a retrieval strategy.
            </p>
            <Button variant="outline" className="mt-7" asChild>
              <Link href="/search">
                Try semantic search <ArrowRight className="size-3.5" />
              </Link>
            </Button>
          </Reveal>

          <Reveal delay={0.1} className="space-y-3">
            {[
              { n: "1", t: "Clause search", d: "Semantic search across every ingested clause, filterable by category, contract and risk level." },
              { n: "2", t: "Similar-clause matching", d: "Comparable clauses from other contracts ground risk scoring in precedent — self-matches excluded." },
              { n: "3", t: "Playbook RAG", d: "Retrieves the handful of rules relevant to a clause instead of pushing the whole playbook into every prompt." },
              { n: "4", t: "Precedent Recall", d: "Closest previously approved wording, surfaced as recommended language." },
              { n: "5", t: "Negotiation memory", d: "How comparable disputes settled, fed to both negotiators and the Strategy Coach." },
            ].map((item) => (
              <Card key={item.n} className="flex items-start gap-4 py-4">
                <span className="numeric grid size-7 shrink-0 place-items-center rounded-md bg-accent/12 text-xs font-bold text-accent-soft">
                  {item.n}
                </span>
                <div>
                  <p className="text-sm font-medium text-silver-100">{item.t}</p>
                  <p className="mt-1 text-xs leading-relaxed text-silver-400">{item.d}</p>
                </div>
              </Card>
            ))}
          </Reveal>
        </div>
      </section>

      {/* ── guardrails ── */}
      <section className="container py-20 sm:py-28">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="eyebrow mb-3">Guardrails</p>
          <h2 className="text-3xl font-semibold tracking-tight text-silver-50 sm:text-4xl">
            An agent that edits contracts needs a leash
          </h2>
          <p className="mt-4 text-base leading-relaxed text-silver-400">
            Each guardrail returns a structured verdict with the matched evidence. See every one
            fire on live input.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-3 sm:grid-cols-2">
          {GUARDRAILS.map((guardrail, i) => (
            <Reveal key={guardrail.title} delay={i * 0.06}>
              <Card hover className="h-full">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" />
                  <div>
                    <h3 className="text-sm font-semibold text-silver-100">{guardrail.title}</h3>
                    <p className="mt-1.5 text-xs leading-relaxed text-silver-400">{guardrail.body}</p>
                  </div>
                </div>
              </Card>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2} className="mt-10 text-center">
          <Button variant="outline" asChild>
            <Link href="/guardrails">
              Open the guardrail demo <ArrowRight className="size-3.5" />
            </Link>
          </Button>
        </Reveal>
      </section>

      {/* ── cta ── */}
      <section className="container pb-24">
        <Reveal>
          <Card className="relative overflow-hidden border-accent/20 bg-gradient-to-br from-accent/[0.10] via-base-800/60 to-base-800/60 p-10 text-center sm:p-16">
            <Boxes className="mx-auto mb-5 size-9 text-accent" />
            <h2 className="text-3xl font-semibold tracking-tight text-silver-50 sm:text-4xl">
              Review your first contract in under a minute
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-silver-400">
              Load the bundled sample agreement — deliberately awful, 17 clauses — and watch the
              agents take it apart.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Button variant="primary" size="lg" asChild>
                <Link href="/signin">
                  Sign in and start <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button variant="secondary" size="lg" asChild>
                <Link href="/upload">Upload a contract</Link>
              </Button>
            </div>
          </Card>
        </Reveal>
      </section>

      <footer className="border-t border-silver-50/[0.05] py-8">
        <div className="container flex flex-wrap items-center justify-between gap-4">
          <Logo />
          <p className="text-2xs text-silver-600">
            Built for the Legal track · Lyzr multi-agent framework · Qdrant · FastAPI · Next.js 15
          </p>
        </div>
      </footer>
    </div>
  );
}

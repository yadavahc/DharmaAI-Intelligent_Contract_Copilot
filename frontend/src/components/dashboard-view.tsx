"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BrainCircuit,
  FileText,
  Layers,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  Upload,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";

import { AnimatedNumber, Stagger, StaggerItem } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  CardTitle,
  EmptyState,
  RiskBadge,
  Skeleton,
  SkeletonCard,
} from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { DashboardData, RiskLevel } from "@/lib/types";
import {
  CHART_PALETTE,
  RISK_COLORS,
  actorClasses,
  cn,
  formatRelative,
  riskClasses,
  truncate,
} from "@/lib/utils";

export function DashboardView() {
  const [data, setData] = React.useState<DashboardData | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [seeding, setSeeding] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setError(null);
      setData(await api.dashboard());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const loadSample = async () => {
    setSeeding(true);
    try {
      const { contract_id } = await api.loadSampleContract();
      toast.success("Sample contract loaded", {
        description: "Open it to run the agent review.",
        action: {
          label: "Open",
          onClick: () => {
            window.location.href = `/contracts/${contract_id}`;
          },
        },
      });
      await load();
    } catch (err) {
      toast.error("Could not load the sample", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    } finally {
      setSeeding(false);
    }
  };

  if (loading) return <DashboardSkeleton />;

  if (error) {
    return (
      <Alert variant="danger" title="Cannot reach the backend" icon={<ShieldAlert className="size-4" />}>
        {error}
        <div className="mt-3">
          <Button size="sm" variant="secondary" onClick={load}>
            <RefreshCw className="size-3.5" /> Retry
          </Button>
        </div>
      </Alert>
    );
  }

  if (!data) return null;

  const { kpis } = data;
  const isEmpty = kpis.contracts === 0;

  const riskData = (Object.keys(RISK_COLORS) as RiskLevel[])
    .map((level) => ({ name: level, value: data.risk_distribution[level] ?? 0 }))
    .filter((d) => d.value > 0);

  const categoryData = Object.entries(data.category_distribution)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8)
    .map(([name, value]) => ({ name, value }));

  const negotiationData = Object.entries(data.negotiation_status).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
  }));

  const confidenceData = Object.entries(data.confidence_buckets).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <div className="space-y-6">
      {/* ── header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-1.5">Overview</p>
          <h1 className="text-3xl font-semibold tracking-tight text-silver-50">Dashboard</h1>
          <p className="mt-1.5 text-sm text-silver-400">
            Portfolio risk, agent activity, and what needs a human.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={load}>
            <RefreshCw className="size-3.5" /> Refresh
          </Button>
          <Button variant="secondary" size="sm" asChild>
            <Link href="/upload">
              <Upload className="size-3.5" /> Upload
            </Link>
          </Button>
          {isEmpty && (
            <Button variant="primary" size="sm" onClick={loadSample} loading={seeding}>
              <Sparkles className="size-3.5" /> Load sample contract
            </Button>
          )}
        </div>
      </div>

      {isEmpty ? (
        <EmptyState
          icon={<FileText className="size-5" />}
          title="No contracts yet"
          description="Load the bundled sample agreement — 17 clauses, deliberately awful — or upload your own PDF/DOCX to watch the agents work."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="primary" onClick={loadSample} loading={seeding}>
                <Sparkles className="size-4" /> Load sample contract
              </Button>
              <Button variant="secondary" asChild>
                <Link href="/upload">Upload your own</Link>
              </Button>
            </div>
          }
        />
      ) : (
        <>
          {/* ── KPI row ── */}
          <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <KpiCard
              label="Contracts"
              value={kpis.contracts}
              icon={FileText}
              href="/contracts"
            />
            <KpiCard label="Clauses reviewed" value={kpis.clauses} icon={Layers} />
            <KpiCard
              label="Portfolio risk"
              value={kpis.avg_contract_risk}
              decimals={1}
              suffix="/100"
              icon={TrendingDown}
              tone={
                kpis.avg_contract_risk >= 70
                  ? "critical"
                  : kpis.avg_contract_risk >= 40
                    ? "medium"
                    : "low"
              }
            />
            <KpiCard
              label="High-risk clauses"
              value={kpis.high_risk_clauses}
              icon={AlertTriangle}
              tone={kpis.high_risk_clauses > 0 ? "high" : "low"}
            />
            <KpiCard
              label="Awaiting review"
              value={kpis.open_reviews}
              icon={BadgeCheck}
              href="/review"
              tone={kpis.open_reviews > 0 ? "medium" : "low"}
            />
            <KpiCard
              label="AI confidence"
              value={kpis.avg_confidence * 100}
              decimals={0}
              suffix="%"
              icon={BrainCircuit}
            />
          </Stagger>

          {/* ── charts ── */}
          <div className="grid gap-4 lg:grid-cols-3">
            {/* risk distribution */}
            <Card className="lg:col-span-1">
              <CardHeader>
                <div>
                  <CardTitle>Risk distribution</CardTitle>
                  <p className="mt-1 text-2xs text-silver-500">Clauses by risk level</p>
                </div>
              </CardHeader>
              {riskData.length === 0 ? (
                <p className="py-10 text-center text-xs text-silver-500">No scored clauses yet.</p>
              ) : (
                <>
                  <div className="h-52">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={riskData}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={54}
                          outerRadius={82}
                          paddingAngle={3}
                          strokeWidth={0}
                        >
                          {riskData.map((entry) => (
                            <Cell key={entry.name} fill={RISK_COLORS[entry.name as RiskLevel]} />
                          ))}
                        </Pie>
                        <RechartsTooltip content={<ChartTooltip />} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <ul className="mt-3 space-y-1.5">
                    {riskData.map((entry) => (
                      <li key={entry.name} className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-silver-300">
                          <span
                            className="size-2 rounded-full"
                            style={{ background: RISK_COLORS[entry.name as RiskLevel] }}
                          />
                          {entry.name}
                        </span>
                        <span className="numeric text-silver-200">{entry.value}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Card>

            {/* category mix */}
            <Card className="lg:col-span-2">
              <CardHeader>
                <div>
                  <CardTitle>Clause categories</CardTitle>
                  <p className="mt-1 text-2xs text-silver-500">
                    Assigned by the Clause Classification Agent
                  </p>
                </div>
              </CardHeader>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={categoryData} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "hsl(var(--silver-500))", fontSize: 10 }}
                      axisLine={false}
                      tickLine={false}
                      interval={0}
                      angle={-28}
                      textAnchor="end"
                      height={58}
                    />
                    <YAxis
                      tick={{ fill: "hsl(var(--silver-500))", fontSize: 10 }}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <RechartsTooltip content={<ChartTooltip />} cursor={{ fill: "hsl(var(--base-700) / 0.4)" }} />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {categoryData.map((entry, i) => (
                        <Cell key={entry.name} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            {/* negotiation status */}
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Negotiation outcomes</CardTitle>
                  <p className="mt-1 text-2xs text-silver-500">Two-agent loop results</p>
                </div>
                <Button variant="ghost" size="icon-sm" asChild>
                  <Link href="/negotiations" aria-label="All negotiations">
                    <ArrowRight className="size-3.5" />
                  </Link>
                </Button>
              </CardHeader>
              {negotiationData.length === 0 ? (
                <EmptyState
                  title="No negotiations yet"
                  description="Open a high-risk clause and start the agent negotiation."
                  className="border-0 py-8"
                />
              ) : (
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={negotiationData}
                      layout="vertical"
                      margin={{ top: 0, right: 12, left: 0, bottom: 0 }}
                    >
                      <XAxis type="number" hide allowDecimals={false} />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fill: "hsl(var(--silver-400))", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        width={78}
                      />
                      <RechartsTooltip content={<ChartTooltip />} cursor={{ fill: "hsl(var(--base-700) / 0.4)" }} />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={18}>
                        {negotiationData.map((entry, i) => (
                          <Cell
                            key={entry.name}
                            fill={
                              entry.name === "Accepted"
                                ? RISK_COLORS.Low
                                : entry.name === "Escalated"
                                  ? RISK_COLORS.High
                                  : entry.name === "Rejected"
                                    ? RISK_COLORS.Critical
                                    : CHART_PALETTE[i % CHART_PALETTE.length]
                            }
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            {/* AI confidence */}
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>AI confidence</CardTitle>
                  <p className="mt-1 text-2xs text-silver-500">
                    Clause classification confidence spread
                  </p>
                </div>
              </CardHeader>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={confidenceData} margin={{ top: 6, right: 8, left: -22, bottom: 0 }}>
                    <defs>
                      <linearGradient id="confGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity={0.45} />
                        <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "hsl(var(--silver-500))", fontSize: 10 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: "hsl(var(--silver-500))", fontSize: 10 }}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <RechartsTooltip content={<ChartTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="hsl(var(--accent))"
                      strokeWidth={2}
                      fill="url(#confGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-2xs leading-relaxed text-silver-500">
                Clauses below 70% are flagged by the hallucination guardrail and surfaced for
                review.
              </p>
            </Card>

            {/* agent telemetry */}
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Agent activity</CardTitle>
                  <p className="mt-1 text-2xs text-silver-500">LLM calls this session</p>
                </div>
              </CardHeader>
              <div className="grid grid-cols-2 gap-3">
                <Metric label="Total calls" value={data.agent_telemetry.total_calls} />
                <Metric
                  label="Avg latency"
                  value={data.agent_telemetry.avg_duration_ms}
                  suffix="ms"
                />
                <Metric
                  label="Prompt tokens"
                  value={data.agent_telemetry.total_prompt_tokens}
                />
                <Metric
                  label="Errors"
                  value={data.agent_telemetry.errors}
                  tone={data.agent_telemetry.errors > 0 ? "critical" : "low"}
                />
              </div>
              {Object.keys(data.agent_telemetry.by_agent).length > 0 && (
                <ul className="mt-4 space-y-1.5 border-t border-silver-50/[0.06] pt-3">
                  {Object.entries(data.agent_telemetry.by_agent)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 5)
                    .map(([agent, count]) => (
                      <li key={agent} className="flex items-center justify-between gap-2 text-2xs">
                        <span className="truncate text-silver-400">{agent}</span>
                        <span className="numeric shrink-0 text-silver-300">{count}</span>
                      </li>
                    ))}
                </ul>
              )}
            </Card>
          </div>

          {/* ── top risks + activity ── */}
          <div className="grid gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader>
                <div>
                  <CardTitle>Highest-risk clauses</CardTitle>
                  <p className="mt-1 text-2xs text-silver-500">Across the whole portfolio</p>
                </div>
              </CardHeader>
              <ul className="divide-y divide-silver-50/[0.05]">
                {data.top_risk_clauses.map((clause) => (
                  <li key={clause.id}>
                    <Link
                      href={`/clauses/${clause.id}`}
                      className="group flex items-start gap-3 py-3 transition-colors hover:bg-base-800/40"
                    >
                      <span
                        className={cn(
                          "numeric mt-0.5 grid size-9 shrink-0 place-items-center rounded-md text-xs font-bold",
                          riskClasses(clause.risk_level).bg,
                          riskClasses(clause.risk_level).text,
                        )}
                      >
                        {Math.round(clause.risk_score)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-xs font-medium text-silver-100 group-hover:text-accent-soft">
                            {clause.heading || "Untitled clause"}
                          </p>
                          <Badge variant="neutral" size="sm">
                            {clause.category}
                          </Badge>
                        </div>
                        <p className="mt-1 line-clamp-2 text-2xs leading-relaxed text-silver-500">
                          {truncate(clause.explanation, 160)}
                        </p>
                      </div>
                      <RiskBadge level={clause.risk_level} size="sm" className="mt-0.5 shrink-0" />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader>
                <div>
                  <CardTitle>Recent activity</CardTitle>
                  <p className="mt-1 text-2xs text-silver-500">From the audit log</p>
                </div>
                <Button variant="ghost" size="icon-sm" asChild>
                  <Link href="/audit" aria-label="Full audit log">
                    <ArrowRight className="size-3.5" />
                  </Link>
                </Button>
              </CardHeader>
              <ul className="space-y-3">
                {data.recent_activity.slice(0, 8).map((event) => {
                  const actor = actorClasses(event.actor_type);
                  return (
                    <li key={event.id} className="flex gap-2.5">
                      <span
                        className={cn(
                          "mt-1 grid size-6 shrink-0 place-items-center rounded-md border text-[0.5rem] font-bold uppercase",
                          actor.bg,
                          actor.border,
                          actor.text,
                        )}
                      >
                        {event.actor_type === "ai_agent" ? "AI" : event.actor_type === "human" ? "HU" : "SY"}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-2xs leading-relaxed text-silver-300">
                          {truncate(event.summary, 130)}
                        </p>
                        <p className="mt-0.5 text-[0.625rem] text-silver-600">
                          {formatRelative(event.timestamp)} · {event.event_type}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

/* ── pieces ─────────────────────────────────────────────────────────────── */

function KpiCard({
  label,
  value,
  icon: Icon,
  decimals = 0,
  suffix = "",
  tone,
  href,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  decimals?: number;
  suffix?: string;
  tone?: "low" | "medium" | "high" | "critical";
  href?: string;
}) {
  const toneText =
    tone === "critical"
      ? "text-risk-critical"
      : tone === "high"
        ? "text-risk-high"
        : tone === "medium"
          ? "text-risk-medium"
          : tone === "low"
            ? "text-risk-low"
            : "text-silver-50";

  const inner = (
    <Card hover={!!href} className="h-full">
      <div className="flex items-start justify-between">
        <p className="text-2xs uppercase tracking-wider text-silver-500">{label}</p>
        <Icon className={cn("size-3.5 shrink-0", tone ? toneText : "text-silver-500")} />
      </div>
      <p className={cn("numeric mt-3 text-2xl font-semibold", toneText)}>
        <AnimatedNumber value={value} decimals={decimals} suffix={suffix} />
      </p>
    </Card>
  );

  return (
    <StaggerItem>
      {href ? (
        <Link href={href} className="block h-full">
          {inner}
        </Link>
      ) : (
        inner
      )}
    </StaggerItem>
  );
}

function Metric({
  label,
  value,
  suffix = "",
  tone,
}: {
  label: string;
  value: number;
  suffix?: string;
  tone?: "low" | "critical";
}) {
  return (
    <div className="rounded-md border border-silver-50/[0.06] bg-base-900/40 p-2.5">
      <p className="text-[0.625rem] uppercase tracking-wider text-silver-500">{label}</p>
      <p
        className={cn(
          "numeric mt-1 text-base font-semibold",
          tone === "critical" ? "text-risk-critical" : "text-silver-100",
        )}
      >
        <AnimatedNumber value={value} suffix={suffix} />
      </p>
    </div>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number; payload?: { name?: string } }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const entry = payload[0];
  const name = label ?? entry.payload?.name ?? entry.name;
  return (
    <div className="rounded-md border border-silver-50/10 bg-base-850/95 px-2.5 py-1.5 shadow-glass-lg backdrop-blur">
      <p className="text-2xs font-medium text-silver-200">{name}</p>
      <p className="numeric text-2xs text-accent-soft">{entry.value}</p>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-3 w-20" />
        <Skeleton className="mt-3 h-8 w-48" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i}>
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className="mt-4 h-7 w-20" />
          </Card>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <SkeletonCard lines={6} />
        <SkeletonCard lines={6} className="lg:col-span-2" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <SkeletonCard lines={4} />
        <SkeletonCard lines={4} />
        <SkeletonCard lines={4} />
      </div>
    </div>
  );
}

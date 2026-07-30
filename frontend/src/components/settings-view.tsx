"use client";

import {
  ArrowRight,
  Bot,
  Cpu,
  Database,
  GitBranch,
  Layers,
  RefreshCw,
  Server,
  Trash2,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useSession } from "next-auth/react";
import * as React from "react";
import { toast } from "sonner";

import { Collapse, PageTransition, Stagger, StaggerItem } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  SectionHeading,
  SkeletonCard,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { AgentCard, HealthResponse, LyzrPipelineDemo } from "@/lib/types";
import { ROLE_LABELS, cn } from "@/lib/utils";

/**
 * Settings — and the page a judge should open to verify the Lyzr claim.
 *
 * Shows the live runtime report, every agent's Lyzr role/persona/task
 * instructions, and a button that runs a genuine `LinearSyncPipeline` and prints
 * each task with its `input_tasks` wiring.
 */
export function SettingsView() {
  const { data: session } = useSession();
  const role = session?.user?.role ?? "BUSINESS_USER";

  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const [agents, setAgents] = React.useState<AgentCard[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [pipeline, setPipeline] = React.useState<LyzrPipelineDemo | null>(null);
  const [runningPipeline, setRunningPipeline] = React.useState(false);
  const [resetting, setResetting] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setError(null);
      const [healthResponse, agentsResponse] = await Promise.all([api.health(), api.agents()]);
      setHealth(healthResponse);
      setAgents(agentsResponse.agents);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const runPipeline = async () => {
    setRunningPipeline(true);
    try {
      setPipeline(await api.lyzrPipelineDemo());
      toast.success("Lyzr pipeline executed");
    } catch (err) {
      toast.error("Pipeline run failed", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    } finally {
      setRunningPipeline(false);
    }
  };

  const reset = async () => {
    if (
      !window.confirm(
        "Delete all contracts, clauses, negotiations and audit entries, then reseed reference data?",
      )
    )
      return;
    setResetting(true);
    try {
      await api.demoReset(false);
      toast.success("Demo data reset");
      await load();
    } catch (err) {
      toast.error("Reset failed", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    } finally {
      setResetting(false);
    }
  };

  return (
    <PageTransition>
      <SectionHeading
        eyebrow="System"
        title="Settings"
        description="Runtime status, the Lyzr agent roster, and demo controls."
        action={
          <Button variant="ghost" size="sm" onClick={load}>
            <RefreshCw className="size-3.5" /> Refresh
          </Button>
        }
      />

      {error && (
        <Alert variant="danger" className="mb-5">
          {error}
        </Alert>
      )}

      {/* ── session ── */}
      <Card className="mb-5">
        <CardTitle className="mb-3">Your session</CardTitle>
        <dl className="grid gap-4 sm:grid-cols-3">
          {[
            ["Signed in as", session?.user?.email ?? "—"],
            ["Name", session?.user?.name ?? "—"],
            ["Role", ROLE_LABELS[role] ?? role],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-2xs uppercase tracking-wider text-silver-500">{label}</dt>
              <dd className="mt-1 truncate text-sm text-silver-100">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 border-t border-silver-50/[0.06] pt-3 text-2xs leading-relaxed text-silver-500">
          {role === "ADMIN"
            ? "As an Admin you can manage the playbook, delete contracts and act on the approval gate."
            : role === "REVIEWER"
              ? "As a Reviewer you can approve, edit or reject redlines, and roll back clause versions."
              : "As a Business User you can upload contracts and read reviews, but not approve redlines."}
        </p>
      </Card>

      {/* ── runtime ── */}
      {!health ? (
        <SkeletonCard lines={5} className="mb-5" />
      ) : (
        <Stagger className="mb-5 grid gap-4 lg:grid-cols-2">
          {/* Lyzr */}
          <StaggerItem>
            <Card className={cn(health.lyzr.is_genuine_sdk ? "border-accent/25" : "border-risk-medium/25")}>
              <div className="mb-3 flex items-center gap-2">
                <Workflow className="size-3.5 text-accent" />
                <CardTitle>Lyzr runtime</CardTitle>
                <Badge
                  variant={health.lyzr.is_genuine_sdk ? "accent" : "medium"}
                  size="sm"
                  className="ml-auto"
                >
                  {health.lyzr.is_genuine_sdk ? "genuine SDK" : "compatibility shim"}
                </Badge>
              </div>

              <dl className="space-y-2">
                {[
                  ["Runtime", `${health.lyzr.lyzr_runtime}${health.lyzr.lyzr_version ? ` v${health.lyzr.lyzr_version}` : ""}`],
                  ["Agent class", health.lyzr.agent_class],
                  ["Task class", health.lyzr.task_class],
                  ["Pipeline class", health.lyzr.pipeline_class],
                  ["AIModel ABC", health.lyzr.ai_model_abc],
                ].map(([label, value]) => (
                  <div key={label} className="flex flex-wrap items-baseline gap-2">
                    <dt className="w-24 shrink-0 text-2xs uppercase tracking-wider text-silver-500">
                      {label}
                    </dt>
                    <dd className="min-w-0 break-all font-mono text-2xs text-silver-300">{value}</dd>
                  </div>
                ))}
              </dl>

              {!health.lyzr.is_genuine_sdk && health.lyzr.import_error && (
                <Alert variant="warning" className="mt-3" title="SDK not importable">
                  {health.lyzr.import_error}
                  <p className="mt-1.5 font-mono text-[0.625rem]">
                    pip install --no-deps --ignore-requires-python -r requirements-lyzr.txt
                  </p>
                </Alert>
              )}

              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={runPipeline}
                loading={runningPipeline}
              >
                <GitBranch className="size-3.5" /> Run a live Lyzr pipeline
              </Button>
            </Card>
          </StaggerItem>

          {/* infra */}
          <StaggerItem>
            <Card>
              <div className="mb-3 flex items-center gap-2">
                <Server className="size-3.5 text-accent" />
                <CardTitle>Infrastructure</CardTitle>
                <Badge
                  variant={health.demo_mode ? "medium" : "low"}
                  size="sm"
                  className="ml-auto"
                >
                  {health.demo_mode ? "demo mode" : "live"}
                </Badge>
              </div>

              <dl className="space-y-2.5">
                <Row
                  icon={Database}
                  label="Database"
                  value={health.database.backend}
                  note={
                    health.database.backend === "sqlite"
                      ? "Postgres unreachable — using the SQLite fallback."
                      : undefined
                  }
                  ok={health.database.connected}
                />
                <Row
                  icon={Layers}
                  label="Vector store"
                  value={health.vector_store.backend}
                  note={
                    health.vector_store.backend === "in-memory"
                      ? "Qdrant unreachable — retrieval works but vectors are not persisted."
                      : undefined
                  }
                  ok={health.vector_store.backend === "qdrant"}
                />
                <Row
                  icon={Cpu}
                  label="LLM"
                  value={health.demo_mode ? "deterministic fixtures" : health.model}
                  note={
                    health.demo_mode
                      ? "No OpenAI calls. Set OPENAI_API_KEY and DHARMA_DEMO_MODE=false for live agents."
                      : undefined
                  }
                  ok={!health.demo_mode}
                />
                <Row
                  icon={Layers}
                  label="Embeddings"
                  value={health.vector_store.embedding_method}
                  ok={health.vector_store.embedding_method.startsWith("openai")}
                />
              </dl>

              {/* collections */}
              <div className="mt-4 border-t border-silver-50/[0.06] pt-3">
                <p className="eyebrow mb-2">Qdrant collections</p>
                <ul className="space-y-1.5">
                  {Object.entries(health.vector_store.collections).map(([name, info]) => (
                    <li key={name} className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-mono text-2xs text-silver-300">{name}</p>
                        <p className="text-[0.625rem] leading-relaxed text-silver-600">
                          {info.purpose}
                        </p>
                      </div>
                      <span className="numeric shrink-0 text-2xs text-silver-400">
                        {info.points}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>
          </StaggerItem>
        </Stagger>
      )}

      {/* ── live pipeline output ── */}
      <Collapse open={!!pipeline}>
        {pipeline && (
          <Card className="mb-5 border-accent/25">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <GitBranch className="size-3.5 text-accent" />
              <CardTitle>Live Lyzr pipeline execution</CardTitle>
              <Badge variant="accent" size="sm">
                {pipeline.task_count} tasks · {pipeline.duration_ms}ms
              </Badge>
            </div>
            <p className="mb-3 break-all font-mono text-2xs text-silver-500">
              {pipeline.pipeline_class}
            </p>

            <ol className="space-y-2.5">
              {pipeline.tasks.map((task, i) => (
                <li
                  key={task.task_id}
                  className="rounded-lg border border-silver-50/[0.06] bg-base-900/50 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="numeric text-2xs font-bold text-accent">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="font-mono text-2xs font-semibold text-silver-100">
                      {task.task_name}
                    </span>
                    <Badge variant="neutral" size="sm">
                      {task.agent_role}
                    </Badge>
                    {task.input_tasks.length > 0 && (
                      <span className="flex items-center gap-1 text-[0.625rem] text-silver-500">
                        <ArrowRight className="size-2.5" />
                        input_tasks: {task.input_tasks.join(", ")}
                      </span>
                    )}
                  </div>
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[0.625rem] font-semibold uppercase tracking-wider text-silver-500">
                      Output
                    </summary>
                    <pre className="mt-1.5 max-h-48 overflow-auto rounded-md bg-base-950/60 p-2.5 font-mono text-[0.625rem] leading-relaxed text-silver-400">
                      {task.output_parsed
                        ? JSON.stringify(task.output_parsed, null, 2)
                        : task.output_raw}
                    </pre>
                  </details>
                </li>
              ))}
            </ol>
          </Card>
        )}
      </Collapse>

      {/* ── agent roster ── */}
      <div className="mb-5">
        <div className="mb-3 flex items-center gap-2">
          <Bot className="size-4 text-accent" />
          <h2 className="text-lg font-semibold text-silver-100">Agent roster</h2>
          {agents && (
            <Badge variant="neutral" size="sm">
              {agents.length} agents
            </Badge>
          )}
        </div>
        <p className="mb-4 max-w-2xl text-xs leading-relaxed text-silver-400">
          Every agent&apos;s Lyzr role, persona and task instructions, exactly as registered in the
          running backend.
        </p>

        {!agents ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} lines={3} />
            ))}
          </div>
        ) : (
          <Stagger className="space-y-2.5">
            {agents.map((agent) => (
              <StaggerItem key={agent.key}>
                <AgentRow agent={agent} />
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </div>

      {/* ── danger zone ── */}
      {role === "ADMIN" && (
        <Card className="border-risk-critical/25">
          <CardTitle className="mb-2">Danger zone</CardTitle>
          <p className="mb-4 text-xs leading-relaxed text-silver-400">
            Deletes every contract, clause, negotiation and audit entry, then reseeds the default
            playbook and precedent library. Useful before a demo run.
          </p>
          <Button variant="danger" onClick={reset} loading={resetting}>
            <Trash2 className="size-4" /> Reset all demo data
          </Button>
        </Card>
      )}
    </PageTransition>
  );
}

function Row({
  icon: Icon,
  label,
  value,
  note,
  ok,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  note?: string;
  ok?: boolean;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon className="mt-0.5 size-3.5 shrink-0 text-silver-500" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-2xs uppercase tracking-wider text-silver-500">{label}</span>
          <span
            className={cn(
              "font-mono text-2xs",
              ok === false ? "text-risk-medium" : "text-silver-200",
            )}
          >
            {value}
          </span>
        </div>
        {note && <p className="mt-0.5 text-[0.625rem] leading-relaxed text-silver-600">{note}</p>}
      </div>
    </div>
  );
}

function AgentRow({ agent }: { agent: AgentCard }) {
  const [open, setOpen] = React.useState(false);

  return (
    <Card flush className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full px-4 py-3 text-left transition-colors hover:bg-base-800/40"
        aria-expanded={open}
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-silver-100">{agent.name}</p>
          <code className="font-mono text-[0.625rem] text-accent-soft">{agent.role}</code>
          {agent.uses_qdrant && (
            <Badge variant="accent" size="sm">
              <Database className="size-2.5" /> Qdrant
            </Badge>
          )}
        </div>
        <p className="mt-1.5 text-2xs leading-relaxed text-silver-400">{agent.outputs}</p>
      </button>

      <Collapse open={open}>
        <div className="space-y-3 border-t border-silver-50/[0.06] px-4 py-3">
          <Field label="Lyzr Agent.prompt_persona" value={agent.persona} italic />
          <Field label="Lyzr Task.instructions" value={agent.instructions} />
          {agent.qdrant_purpose && (
            <Field label="Qdrant usage" value={agent.qdrant_purpose} />
          )}
          {agent.hands_off_to.length > 0 && (
            <div>
              <p className="mb-1.5 text-[0.625rem] uppercase tracking-wider text-silver-600">
                Hands off to
              </p>
              <div className="flex flex-wrap gap-1.5">
                {agent.hands_off_to.map((next) => (
                  <Badge key={next} variant="neutral" size="sm">
                    {next}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </Collapse>
    </Card>
  );
}

function Field({
  label,
  value,
  italic = false,
}: {
  label: string;
  value: string;
  italic?: boolean;
}) {
  return (
    <div>
      <p className="mb-1 text-[0.625rem] uppercase tracking-wider text-silver-600">{label}</p>
      <p
        className={cn(
          "rounded-md border border-silver-50/[0.06] bg-base-900/50 p-2.5 text-2xs leading-relaxed text-silver-300",
          italic && "italic",
        )}
      >
        {value}
      </p>
    </div>
  );
}

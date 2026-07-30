"use client";

import {
  Activity,
  BadgeCheck,
  Bot,
  ChevronDown,
  Cog,
  Link2,
  ShieldAlert,
  ShieldCheck,
  User,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { AnimatedNumber, Collapse, PageTransition } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  Input,
  SectionHeading,
  Select,
  SkeletonCard,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { AuditEvent, ChainVerification } from "@/lib/types";
import { actorClasses, cn, formatDateTime, formatRelative, titleCase } from "@/lib/utils";

const PAGE_SIZE = 40;

export function AuditLogView() {
  const [events, setEvents] = React.useState<AuditEvent[] | null>(null);
  const [total, setTotal] = React.useState(0);
  const [offset, setOffset] = React.useState(0);
  const [actorFilter, setActorFilter] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [verification, setVerification] = React.useState<ChainVerification | null>(null);
  const [verifying, setVerifying] = React.useState(false);
  const [stats, setStats] = React.useState<Awaited<ReturnType<typeof api.auditStats>> | null>(null);

  const load = React.useCallback(async () => {
    try {
      setError(null);
      const [response, statsResponse] = await Promise.all([
        api.audit({
          limit: PAGE_SIZE,
          offset,
          actor_type: actorFilter || undefined,
        }),
        api.auditStats().catch(() => null),
      ]);
      setEvents(response.events);
      setTotal(response.total);
      if (statsResponse) setStats(statsResponse);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setEvents([]);
    }
  }, [offset, actorFilter]);

  React.useEffect(() => {
    load();
  }, [load]);

  const verify = async () => {
    setVerifying(true);
    try {
      const result = await api.verifyAudit();
      setVerification(result);
      if (result.valid) {
        toast.success("Chain verified", {
          description: `All ${result.entries_checked} entries hash correctly and link to their predecessor.`,
        });
      } else {
        toast.error("Chain verification FAILED", {
          description: `${result.problems.length} problem(s) found — entries were altered.`,
        });
      }
    } catch (err) {
      toast.error("Verification failed", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    } finally {
      setVerifying(false);
    }
  };

  const filtered = React.useMemo(() => {
    if (!events) return [];
    const needle = query.trim().toLowerCase();
    if (!needle) return events;
    return events.filter(
      (e) =>
        e.summary.toLowerCase().includes(needle) ||
        e.event_type.toLowerCase().includes(needle) ||
        e.actor_id.toLowerCase().includes(needle),
    );
  }, [events, query]);

  return (
    <PageTransition>
      <SectionHeading
        eyebrow="Compliance"
        title="Audit log"
        description="Append-only, hash-chained record of every AI decision and human action. Editing, reordering or removing any entry breaks verification from that point on."
        action={
          <Button variant="primary" size="sm" onClick={verify} loading={verifying} data-testid="verify-chain">
            <ShieldCheck className="size-3.5" /> Verify chain
          </Button>
        }
      />

      {error && (
        <Alert variant="danger" className="mb-5">
          {error}
        </Alert>
      )}

      {/* ── verification result ── */}
      {verification && (
        <Card
          className={cn(
            "mb-5",
            verification.valid ? "border-risk-low/30" : "border-risk-critical/30",
          )}
          data-testid="chain-verification"
        >
          <div className="flex items-start gap-3">
            {verification.valid ? (
              <ShieldCheck className="mt-0.5 size-5 shrink-0 text-risk-low" />
            ) : (
              <ShieldAlert className="mt-0.5 size-5 shrink-0 text-risk-critical" />
            )}
            <div className="min-w-0 flex-1">
              <CardTitle>
                {verification.valid
                  ? "Chain intact — no tampering detected"
                  : "Chain verification failed"}
              </CardTitle>
              <p className="mt-1.5 text-xs leading-relaxed text-silver-400">
                {verification.entries_checked} entries recomputed and checked against their stored
                hashes and predecessor links.
              </p>
              <p className="mt-2 break-all font-mono text-[0.625rem] text-silver-600">
                <Link2 className="mr-1 inline size-2.5" />
                head: {verification.head_hash}
              </p>
              <p className="mt-1 text-[0.625rem] text-silver-600">{verification.algorithm}</p>

              {verification.problems.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {verification.problems.map((problem, i) => (
                    <li
                      key={i}
                      className="rounded-md border border-risk-critical/25 bg-risk-critical/[0.06] p-2.5"
                    >
                      <p className="text-2xs font-semibold text-risk-critical">
                        Entry #{problem.seq} — {titleCase(problem.issue)}
                      </p>
                      <p className="mt-1 text-2xs leading-relaxed text-silver-400">
                        {problem.detail}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* ── stats ── */}
      {stats && (
        <div className="mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <p className="text-2xs uppercase tracking-wider text-silver-500">Total entries</p>
            <p className="numeric mt-2 text-2xl font-semibold text-silver-50">
              <AnimatedNumber value={stats.total_events} />
            </p>
          </Card>
          {[
            { key: "ai_agent", label: "AI decisions", icon: Bot },
            { key: "human", label: "Human actions", icon: User },
            { key: "system", label: "System events", icon: Cog },
          ].map((item) => {
            const Icon = item.icon;
            const actor = actorClasses(item.key);
            return (
              <Card key={item.key}>
                <div className="flex items-start justify-between">
                  <p className="text-2xs uppercase tracking-wider text-silver-500">{item.label}</p>
                  <Icon className={cn("size-3.5", actor.text)} />
                </div>
                <p className={cn("numeric mt-2 text-2xl font-semibold", actor.text)}>
                  <AnimatedNumber value={stats.by_actor_type[item.key] ?? 0} />
                </p>
              </Card>
            );
          })}
        </div>
      )}

      {/* ── filters ── */}
      <div className="mb-5 flex flex-wrap gap-3">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter this page by summary, event type or actor"
          className="min-w-56 flex-1"
        />
        <Select
          value={actorFilter}
          onChange={(e) => {
            setActorFilter(e.target.value);
            setOffset(0);
          }}
          className="w-full sm:w-44"
          aria-label="Filter by actor type"
        >
          <option value="">All actors</option>
          <option value="ai_agent">AI agents</option>
          <option value="human">Humans</option>
          <option value="system">System</option>
        </Select>
      </div>

      {/* ── timeline ── */}
      {events === null ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} lines={2} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Activity className="size-5" />}
          title="No audit entries"
          description="Upload and review a contract to generate the trail."
        />
      ) : (
        <>
          <div className="space-y-2">
            {filtered.map((event) => (
              <AuditRow key={event.id} event={event} />
            ))}
          </div>

          {/* pagination */}
          {total > PAGE_SIZE && (
            <div className="mt-6 flex items-center justify-between">
              <p className="text-2xs text-silver-500">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Newer
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Older
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </PageTransition>
  );
}

function AuditRow({ event }: { event: AuditEvent }) {
  const [open, setOpen] = React.useState(false);
  const actor = actorClasses(event.actor_type);
  const Icon = event.actor_type === "ai_agent" ? Bot : event.actor_type === "human" ? User : Cog;

  return (
    <Card flush className="overflow-hidden" data-testid="audit-row">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-base-800/40"
        aria-expanded={open}
      >
        <span className="numeric mt-0.5 w-9 shrink-0 text-2xs text-silver-600">#{event.seq}</span>
        <span
          className={cn(
            "mt-0.5 grid size-7 shrink-0 place-items-center rounded-md border",
            actor.bg,
            actor.border,
            actor.text,
          )}
        >
          <Icon className="size-3.5" />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="neutral" size="sm">
              {event.event_type}
            </Badge>
            <span className={cn("text-[0.625rem] font-semibold uppercase tracking-wider", actor.text)}>
              {actor.label}
            </span>
            {event.actor_role && (
              <span className="text-[0.625rem] text-silver-600">{event.actor_role}</span>
            )}
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-silver-300">{event.summary}</p>
          <p className="mt-1 text-[0.625rem] text-silver-600">
            {formatRelative(event.timestamp)} · {event.actor_id}
          </p>
        </div>

        <ChevronDown
          className={cn(
            "mt-1 size-3.5 shrink-0 text-silver-500 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>

      <Collapse open={open}>
        <div className="space-y-3 border-t border-silver-50/[0.06] px-4 py-3">
          {event.compliance_note && (
            <div className="rounded-md border border-accent/20 bg-accent/[0.04] p-2.5">
              <p className="mb-1 flex items-center gap-1.5 text-[0.625rem] font-semibold uppercase tracking-wider text-accent-soft">
                <BadgeCheck className="size-2.5" /> Compliance note
              </p>
              <p className="text-2xs leading-relaxed text-silver-300">{event.compliance_note}</p>
            </div>
          )}

          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
            {[
              ["Timestamp", formatDateTime(event.timestamp)],
              ["Object", `${event.object_type} ${event.object_id.slice(0, 8)}`],
              ["Contract", event.contract_id ? event.contract_id.slice(0, 8) : "—"],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-[0.625rem] uppercase tracking-wider text-silver-600">{label}</dt>
                <dd className="mt-0.5 font-mono text-2xs text-silver-300">{value}</dd>
              </div>
            ))}
          </dl>

          {/* hash chain */}
          <div className="rounded-md border border-silver-50/[0.06] bg-base-900/50 p-2.5">
            <p className="mb-1.5 text-[0.625rem] uppercase tracking-wider text-silver-600">
              Hash chain
            </p>
            <p className="break-all font-mono text-[0.625rem] leading-relaxed text-silver-500">
              <span className="text-silver-600">prev:</span> {event.prev_hash}
            </p>
            <p className="mt-1 break-all font-mono text-[0.625rem] leading-relaxed text-accent-soft">
              <span className="text-silver-600">this:</span> {event.hash}
            </p>
          </div>

          {Object.keys(event.payload ?? {}).length > 0 && (
            <details>
              <summary className="cursor-pointer text-[0.625rem] font-semibold uppercase tracking-wider text-silver-500">
                Payload
              </summary>
              <pre className="mt-2 max-h-56 overflow-auto rounded-md border border-silver-50/[0.06] bg-base-900/60 p-2.5 font-mono text-[0.625rem] leading-relaxed text-silver-400">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </Collapse>
    </Card>
  );
}

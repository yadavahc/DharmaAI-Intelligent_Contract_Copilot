"use client";

import {
  BadgeCheck,
  Check,
  ChevronDown,
  Gavel,
  Lock,
  MessageSquare,
  Pencil,
  ShieldCheck,
  X,
} from "lucide-react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import * as React from "react";
import { toast } from "sonner";

import { DiffView } from "@/components/diff-view";
import { Collapse, PageTransition } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  RiskBadge,
  SectionHeading,
  Select,
  SkeletonCard,
  Textarea,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { ReviewTask } from "@/lib/types";
import { canApprove, cn, formatRelative, riskClasses, truncate } from "@/lib/utils";

/**
 * The human reviewer queue — where guardrail #4 (the approval gate) is exercised.
 *
 * A Business User can see the queue but cannot act on it: the buttons are
 * disabled *and* the backend refuses the call, so the control does not depend on
 * the UI being honest.
 */
export function ReviewQueueView() {
  const { data: session } = useSession();
  const role = session?.user?.role;
  const mayApprove = canApprove(role);

  const [tasks, setTasks] = React.useState<ReviewTask[] | null>(null);
  const [counts, setCounts] = React.useState<Record<string, number>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [statusFilter, setStatusFilter] = React.useState("open");
  const [priorityFilter, setPriorityFilter] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      setError(null);
      const response = await api.reviewQueue({
        status: statusFilter,
        priority: priorityFilter || undefined,
      });
      setTasks(response.tasks);
      setCounts(response.counts_by_status);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setTasks([]);
    }
  }, [statusFilter, priorityFilter]);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <PageTransition>
      <SectionHeading
        eyebrow="Human-in-the-loop"
        title="Review queue"
        description="Clauses the Escalation Agent routed to a human. No AI redline is finalised until someone here approves, edits or rejects it."
        action={
          <div className="flex gap-2">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-36"
              aria-label="Filter by status"
            >
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="all">All</option>
            </Select>
            <Select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="w-40"
              aria-label="Filter by priority"
            >
              <option value="">All priorities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </Select>
          </div>
        }
      />

      {!mayApprove && (
        <Alert
          variant="info"
          title="Read-only for your role"
          className="mb-5"
          icon={<Lock className="size-3.5" />}
        >
          You are signed in as a Business User. You can read every escalation, but only a Reviewer
          or Admin can act on the approval gate — and the backend enforces that independently of
          this interface.
        </Alert>
      )}

      {error && (
        <Alert variant="danger" className="mb-5">
          {error}
        </Alert>
      )}

      {/* ── status counts ── */}
      {Object.keys(counts).length > 0 && (
        <div className="mb-5 flex flex-wrap gap-2">
          {Object.entries(counts).map(([status, count]) => (
            <Badge key={status} variant={status === "open" ? "high" : "neutral"}>
              {count} {status}
            </Badge>
          ))}
        </div>
      )}

      {tasks === null ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} lines={3} />
          ))}
        </div>
      ) : tasks.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck className="size-5" />}
          title={statusFilter === "open" ? "Nothing awaiting review" : "No tasks match"}
          description={
            statusFilter === "open"
              ? "Every escalated clause has been dealt with. Run a review or a negotiation to generate more."
              : "Try a different status or priority filter."
          }
          action={
            <Button variant="secondary" asChild>
              <Link href="/contracts">Browse contracts</Link>
            </Button>
          }
        />
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <ReviewTaskCard
              key={task.id}
              task={task}
              mayApprove={mayApprove}
              onDecided={load}
            />
          ))}
        </div>
      )}
    </PageTransition>
  );
}

/* ── task card ──────────────────────────────────────────────────────────── */

const PRIORITY_VARIANT: Record<string, "high" | "medium" | "neutral"> = {
  high: "high",
  medium: "medium",
  low: "neutral",
};

function ReviewTaskCard({
  task,
  mayApprove,
  onDecided,
}: {
  task: ReviewTask;
  mayApprove: boolean;
  onDecided: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [editedText, setEditedText] = React.useState(task.redline?.suggested ?? task.clause_text);
  const [mode, setMode] = React.useState<"none" | "edit">("none");
  const [submitting, setSubmitting] = React.useState<string | null>(null);

  const risk = riskClasses(task.risk_level);
  const closed = task.status === "closed";
  const hasRedline = Boolean(task.redline?.suggested);

  const decide = async (decision: "approve" | "reject" | "edit" | "comment") => {
    setSubmitting(decision);
    try {
      const result = await api.decide(task.id, {
        decision,
        note,
        edited_text: decision === "edit" ? editedText : undefined,
      });
      if (decision === "comment") {
        toast.success("Comment recorded", {
          description: "The approval gate remains closed — a comment is not a decision.",
        });
      } else {
        toast.success(`Redline ${decision}d`, {
          description: result.finalized
            ? `Approval gate: ${result.previous_state} → ${result.approval_state}. Wording added to the precedent library.`
            : `Approval gate: ${result.previous_state} → ${result.approval_state}.`,
        });
      }
      setNote("");
      setMode("none");
      onDecided();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : String(err);
      toast.error("Decision refused", { description: message });
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <Card
      flush
      className={cn("overflow-hidden", !closed && task.priority === "high" && "border-risk-high/25")}
      data-testid="review-task"
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
            risk.bg,
            risk.text,
          )}
        >
          {Math.round(task.risk_score)}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-silver-100">
              {task.clause_heading || "Clause"}
            </p>
            <Badge variant={PRIORITY_VARIANT[task.priority] ?? "neutral"} size="sm">
              {task.priority} priority
            </Badge>
            <Badge variant="neutral" size="sm">
              {task.category}
            </Badge>
            <RiskBadge level={task.risk_level} size="sm" />
            {closed && (
              <Badge variant="low" size="sm">
                <Check className="size-2.5" /> {task.decision}d
              </Badge>
            )}
            {task.approval_state === "finalized" && (
              <Badge variant="low" size="sm">
                finalised
              </Badge>
            )}
          </div>
          <p className="mt-1.5 line-clamp-2 text-2xs leading-relaxed text-silver-500">
            {truncate(task.reason, 180)}
          </p>
          <p className="mt-1 text-[0.625rem] text-silver-600">
            {truncate(task.contract_title, 44)} · {formatRelative(task.created_at)}
            {task.sla_hours ? ` · SLA ${task.sla_hours}h` : ""}
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
          {/* what the human must decide */}
          {task.recommended_action && (
            <div className="rounded-lg border border-risk-high/20 bg-risk-high/[0.05] p-3.5">
              <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-risk-high">
                <Gavel className="size-3" /> Decision required
              </p>
              <p className="text-xs leading-relaxed text-silver-300">{task.recommended_action}</p>
            </div>
          )}

          {/* clause text */}
          <div>
            <p className="eyebrow mb-2">Current clause</p>
            <p className="whitespace-pre-wrap rounded-lg border border-silver-50/[0.06] bg-base-900/50 p-3.5 font-mono text-xs leading-relaxed text-silver-300">
              {task.clause_text}
            </p>
          </div>

          {/* redline diff */}
          {hasRedline && (
            <DiffView
              original={task.redline.original ?? task.clause_text}
              suggested={task.redline.suggested ?? ""}
              reason={task.redline.reason}
              changeSummary={task.redline.change_summary}
            />
          )}

          {closed ? (
            <div className="rounded-lg border border-silver-50/[0.06] bg-base-900/40 p-3.5">
              <p className="text-2xs uppercase tracking-wider text-silver-500">Decision</p>
              <p className="mt-1.5 text-xs text-silver-200">
                <span className="font-semibold capitalize">{task.decision}</span> by{" "}
                {task.decided_by} · {formatRelative(task.decided_at)}
              </p>
              {task.decision_note && (
                <p className="mt-1.5 text-2xs italic leading-relaxed text-silver-400">
                  &ldquo;{task.decision_note}&rdquo;
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-3 border-t border-silver-50/[0.06] pt-4">
              <div className="flex items-center gap-2">
                <BadgeCheck className="size-3.5 text-accent" />
                <p className="text-xs font-semibold text-silver-100">Human approval gate</p>
                <Badge variant="medium" size="sm">
                  {task.approval_state?.replace(/_/g, " ") ?? "pending"}
                </Badge>
              </div>

              {mode === "edit" && (
                <div>
                  <p className="eyebrow mb-1.5">Your wording</p>
                  <Textarea
                    value={editedText}
                    onChange={(e) => setEditedText(e.target.value)}
                    rows={6}
                    className="font-mono text-xs"
                  />
                </div>
              )}

              <Textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="Note for the audit record (optional, but recommended)"
                className="text-xs"
              />

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  disabled={!mayApprove || !!submitting}
                  loading={submitting === "approve"}
                  onClick={() => decide("approve")}
                  data-testid="approve-redline"
                >
                  <Check className="size-3.5" /> Approve
                </Button>

                {mode === "edit" ? (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!mayApprove || !!submitting}
                    loading={submitting === "edit"}
                    onClick={() => decide("edit")}
                  >
                    <Check className="size-3.5" /> Save edit and approve
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!mayApprove}
                    onClick={() => setMode("edit")}
                  >
                    <Pencil className="size-3.5" /> Edit wording
                  </Button>
                )}

                <Button
                  variant="danger"
                  size="sm"
                  disabled={!mayApprove || !!submitting}
                  loading={submitting === "reject"}
                  onClick={() => decide("reject")}
                >
                  <X className="size-3.5" /> Reject
                </Button>

                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!mayApprove || !!submitting || !note.trim()}
                  loading={submitting === "comment"}
                  onClick={() => decide("comment")}
                >
                  <MessageSquare className="size-3.5" /> Comment only
                </Button>

                <Button variant="ghost" size="sm" asChild className="ml-auto">
                  <Link href={`/clauses/${task.clause_id}`}>Open clause →</Link>
                </Button>
              </div>

              {!mayApprove && (
                <p className="text-[0.625rem] leading-relaxed text-silver-600">
                  Approving requires the Reviewer or Admin role. The backend returns 403 for any
                  other role, so this is not merely a disabled button.
                </p>
              )}
            </div>
          )}
        </div>
      </Collapse>
    </Card>
  );
}

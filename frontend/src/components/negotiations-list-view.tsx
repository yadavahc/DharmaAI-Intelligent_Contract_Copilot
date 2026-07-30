"use client";

import { ArrowRight, Gavel, Swords, TrendingDown } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { PageTransition, Stagger, StaggerItem } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  SectionHeading,
  Select,
  SkeletonCard,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { Negotiation } from "@/lib/types";
import { cn, formatRelative, riskClasses } from "@/lib/utils";

const OUTCOME_META: Record<
  string,
  { variant: "low" | "medium" | "high" | "critical" | "neutral"; label: string }
> = {
  accepted: { variant: "low", label: "Accepted" },
  escalated: { variant: "high", label: "Escalated" },
  rejected: { variant: "critical", label: "Rejected" },
  pending: { variant: "neutral", label: "Pending" },
};

export function NegotiationsListView() {
  const [negotiations, setNegotiations] = React.useState<Negotiation[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [outcomeFilter, setOutcomeFilter] = React.useState("");

  React.useEffect(() => {
    api
      .negotiations({ limit: 100, outcome: outcomeFilter || undefined })
      .then((r) => setNegotiations(r.negotiations))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : String(err));
        setNegotiations([]);
      });
  }, [outcomeFilter]);

  return (
    <PageTransition>
      <SectionHeading
        eyebrow="Two-agent loop"
        title="Negotiations"
        description="Every negotiation the Organization and Counterparty agents have run, with the risk they removed."
        action={
          <Select
            value={outcomeFilter}
            onChange={(e) => setOutcomeFilter(e.target.value)}
            className="w-44"
            aria-label="Filter by outcome"
          >
            <option value="">All outcomes</option>
            <option value="accepted">Accepted</option>
            <option value="escalated">Escalated</option>
            <option value="rejected">Rejected</option>
          </Select>
        }
      />

      {error && (
        <Alert variant="danger" className="mb-5">
          {error}
        </Alert>
      )}

      {negotiations === null ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} lines={4} />
          ))}
        </div>
      ) : negotiations.length === 0 ? (
        <EmptyState
          icon={<Swords className="size-5" />}
          title="No negotiations yet"
          description="Open a reviewed contract, pick a high-risk clause, and start the agent negotiation to watch it live."
          action={
            <Button variant="primary" asChild>
              <Link href="/contracts">Browse contracts</Link>
            </Button>
          }
        />
      ) : (
        <Stagger className="grid gap-4 md:grid-cols-2">
          {negotiations.map((negotiation) => {
            const meta = OUTCOME_META[negotiation.outcome] ?? OUTCOME_META.pending;
            const reduction =
              negotiation.risk_reduction ??
              (negotiation.initial_risk ?? 0) - (negotiation.final_risk ?? 0);
            const finalRisk = riskClasses(
              negotiation.final_risk >= 90
                ? "Critical"
                : negotiation.final_risk >= 70
                  ? "High"
                  : negotiation.final_risk >= 40
                    ? "Medium"
                    : "Low",
            );

            return (
              <StaggerItem key={negotiation.id}>
                <Link href={`/negotiations/${negotiation.clause_id}`} className="block h-full">
                  <Card hover className="flex h-full flex-col">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={meta.variant} size="sm">
                            {meta.label}
                          </Badge>
                          <Badge variant="neutral" size="sm">
                            {negotiation.category}
                          </Badge>
                          {negotiation.escalated && (
                            <Badge variant="high" size="sm">
                              <Gavel className="size-2.5" /> human review
                            </Badge>
                          )}
                        </div>
                        <p className="mt-2.5 text-2xs text-silver-500">
                          {negotiation.rounds_used} of {negotiation.max_rounds} rounds ·{" "}
                          {formatRelative(negotiation.created_at)}
                        </p>
                      </div>
                      <ArrowRight className="size-3.5 shrink-0 text-silver-600" />
                    </div>

                    {/* risk journey */}
                    <div className="mt-5 flex items-center gap-3">
                      <div className="text-center">
                        <p className="numeric text-lg font-semibold text-silver-400">
                          {negotiation.initial_risk?.toFixed(0)}
                        </p>
                        <p className="text-[0.625rem] text-silver-600">before</p>
                      </div>

                      <div className="relative flex-1">
                        <div className="h-1 rounded-full bg-base-700/70">
                          <div
                            className={cn("h-full rounded-full", finalRisk.dot)}
                            style={{ width: `${negotiation.final_risk ?? 0}%` }}
                          />
                        </div>
                        {reduction > 0 && (
                          <span className="numeric absolute -top-4 left-1/2 flex -translate-x-1/2 items-center gap-0.5 whitespace-nowrap text-[0.625rem] font-semibold text-risk-low">
                            <TrendingDown className="size-2.5" />
                            {reduction.toFixed(1)}
                          </span>
                        )}
                      </div>

                      <div className="text-center">
                        <p className={cn("numeric text-lg font-semibold", finalRisk.text)}>
                          {negotiation.final_risk?.toFixed(0)}
                        </p>
                        <p className="text-[0.625rem] text-silver-600">after</p>
                      </div>
                    </div>
                  </Card>
                </Link>
              </StaggerItem>
            );
          })}
        </Stagger>
      )}
    </PageTransition>
  );
}

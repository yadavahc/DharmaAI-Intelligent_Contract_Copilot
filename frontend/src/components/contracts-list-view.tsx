"use client";

import { FileText, Filter, Search, ShieldAlert, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { PageTransition, Stagger, StaggerItem } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  RiskBadge,
  SectionHeading,
  Select,
  SkeletonCard,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { Contract } from "@/lib/types";
import { RISK_LEVELS, formatRelative, riskClasses } from "@/lib/utils";

export function ContractsListView() {
  const [contracts, setContracts] = React.useState<Contract[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState("");
  const [riskFilter, setRiskFilter] = React.useState("");
  const [loadingSample, setLoadingSample] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setError(null);
      const response = await api.contracts({ limit: 100 });
      setContracts(response.contracts);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setContracts([]);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const loadSample = async () => {
    setLoadingSample(true);
    try {
      const { contract_id } = await api.loadSampleContract();
      toast.success("Sample contract loaded");
      window.location.href = `/contracts/${contract_id}`;
    } catch (err) {
      toast.error("Could not load the sample", {
        description: err instanceof ApiError ? err.message : String(err),
      });
      setLoadingSample(false);
    }
  };

  // Client-side filtering: the list is small enough that a round trip per
  // keystroke would be slower than filtering locally.
  const filtered = React.useMemo(() => {
    if (!contracts) return [];
    const needle = query.trim().toLowerCase();
    return contracts.filter((contract) => {
      if (riskFilter && contract.risk_level !== riskFilter) return false;
      if (!needle) return true;
      return (
        contract.title.toLowerCase().includes(needle) ||
        contract.counterparty.toLowerCase().includes(needle) ||
        contract.filename.toLowerCase().includes(needle)
      );
    });
  }, [contracts, query, riskFilter]);

  return (
    <PageTransition>
      <SectionHeading
        eyebrow="Portfolio"
        title="Contracts"
        description="Every ingested agreement, with its rolled-up risk score."
        action={
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" asChild>
              <Link href="/search">
                <Search className="size-3.5" /> Semantic search
              </Link>
            </Button>
            <Button variant="primary" size="sm" asChild>
              <Link href="/upload">
                <Upload className="size-3.5" /> Upload
              </Link>
            </Button>
          </div>
        }
      />

      {error && (
        <Alert variant="danger" className="mb-5" icon={<ShieldAlert className="size-3.5" />}>
          {error}
        </Alert>
      )}

      {/* ── filters ── */}
      {contracts && contracts.length > 0 && (
        <div className="mb-5 flex flex-wrap gap-3">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-silver-500" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by title, counterparty or filename"
              className="pl-9"
            />
          </div>
          <div className="relative w-full sm:w-52">
            <Filter className="pointer-events-none absolute left-3 top-1/2 z-10 size-3.5 -translate-y-1/2 text-silver-500" />
            <Select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="pl-9"
              aria-label="Filter by risk level"
            >
              <option value="">All risk levels</option>
              {RISK_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level} risk
                </option>
              ))}
            </Select>
          </div>
        </div>
      )}

      {/* ── list ── */}
      {contracts === null ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} lines={4} />
          ))}
        </div>
      ) : contracts.length === 0 ? (
        <EmptyState
          icon={<FileText className="size-5" />}
          title="No contracts yet"
          description="Load the bundled sample agreement or upload a PDF/DOCX to get started."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="primary" onClick={loadSample} loading={loadingSample}>
                <Sparkles className="size-4" /> Load sample contract
              </Button>
              <Button variant="secondary" asChild>
                <Link href="/upload">Upload your own</Link>
              </Button>
            </div>
          }
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Filter className="size-5" />}
          title="No contracts match those filters"
          description="Try a different search term or clear the risk filter."
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setQuery("");
                setRiskFilter("");
              }}
            >
              Clear filters
            </Button>
          }
        />
      ) : (
        <>
          <p className="mb-4 text-2xs text-silver-500">
            {filtered.length} of {contracts.length} contract
            {contracts.length === 1 ? "" : "s"}
          </p>
          <Stagger className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((contract) => {
              const risk = riskClasses(contract.risk_level);
              const reviewed = contract.risk_score > 0;
              return (
                <StaggerItem key={contract.id}>
                  <Link href={`/contracts/${contract.id}`} className="block h-full">
                    <Card hover className="flex h-full flex-col">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-silver-100">
                            {contract.title}
                          </h3>
                          {contract.counterparty && (
                            <p className="mt-1 truncate text-2xs text-silver-500">
                              vs. {contract.counterparty}
                            </p>
                          )}
                        </div>
                        {reviewed ? (
                          <span
                            className={`numeric grid size-11 shrink-0 place-items-center rounded-lg text-sm font-bold ${risk.bg} ${risk.text}`}
                          >
                            {Math.round(contract.risk_score)}
                          </span>
                        ) : (
                          <Badge variant="neutral" size="sm" className="shrink-0">
                            not reviewed
                          </Badge>
                        )}
                      </div>

                      <div className="mt-4 flex flex-wrap gap-1.5">
                        {reviewed && <RiskBadge level={contract.risk_level} size="sm" />}
                        <Badge variant="neutral" size="sm">
                          {contract.clause_count} clauses
                        </Badge>
                        {contract.guardrails_flagged && (
                          <Badge variant="medium" size="sm">
                            <ShieldAlert className="size-2.5" /> guardrail
                          </Badge>
                        )}
                        {contract.has_executive_summary && (
                          <Badge variant="accent" size="sm">
                            brief ready
                          </Badge>
                        )}
                      </div>

                      {/* risk distribution mini-bar */}
                      {reviewed && contract.risk_summary && "distribution" in contract.risk_summary && (
                        <div className="mt-4 flex h-1.5 overflow-hidden rounded-full bg-base-700/60">
                          {RISK_LEVELS.map((level) => {
                            const count =
                              (contract.risk_summary as { distribution: Record<string, number> })
                                .distribution[level] ?? 0;
                            if (!count) return null;
                            const pct = (count / contract.clause_count) * 100;
                            return (
                              <span
                                key={level}
                                className={riskClasses(level).dot}
                                style={{ width: `${pct}%` }}
                                title={`${count} ${level}`}
                              />
                            );
                          })}
                        </div>
                      )}

                      <p className="mt-auto pt-4 text-[0.625rem] text-silver-600">
                        {formatRelative(contract.created_at)} · {contract.uploaded_by}
                      </p>
                    </Card>
                  </Link>
                </StaggerItem>
              );
            })}
          </Stagger>
        </>
      )}
    </PageTransition>
  );
}

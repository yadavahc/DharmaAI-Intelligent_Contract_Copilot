"use client";

import { Database, Library, Search, Swords, BookOpen, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import * as React from "react";

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
import type { SearchResult } from "@/lib/types";
import { RISK_LEVELS, cn, truncate } from "@/lib/utils";

const SCOPES = [
  {
    key: "clauses",
    label: "Clauses",
    icon: Database,
    blurb: "Every ingested clause across all contracts.",
  },
  {
    key: "precedents",
    label: "Precedents",
    icon: Library,
    blurb: "Approved wording available as recommended language.",
  },
  {
    key: "negotiations",
    label: "Negotiation memory",
    icon: Swords,
    blurb: "How comparable disputes actually settled.",
  },
  {
    key: "playbook",
    label: "Playbook rules",
    icon: BookOpen,
    blurb: "Rules retrieved semantically, as the agents see them.",
  },
] as const;

const EXAMPLES = [
  "uncapped liability exposure",
  "automatic renewal without notice",
  "assignment of intellectual property ownership",
  "payment terms beyond net 30",
  "data breach notification obligations",
];

export function SearchView() {
  const [query, setQuery] = React.useState("");
  const [scope, setScope] = React.useState<string>("clauses");
  const [category, setCategory] = React.useState("");
  const [riskLevel, setRiskLevel] = React.useState("");
  const [categories, setCategories] = React.useState<string[]>([]);
  const [results, setResults] = React.useState<SearchResult[] | null>(null);
  const [meta, setMeta] = React.useState<{
    collection: string;
    purpose: string;
    backend: string;
    count: number;
  } | null>(null);
  const [scopeStats, setScopeStats] = React.useState<
    { key: string; points: number; purpose: string }[] | null
  >(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    api.categories().then((r) => setCategories(r.categories)).catch(() => setCategories([]));
    api
      .searchScopes()
      .then((r) => setScopeStats(r.scopes.map((s) => ({ key: s.key, points: s.points, purpose: s.purpose }))))
      .catch(() => setScopeStats(null));
  }, []);

  const run = async (searchQuery = query) => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.search({
        query: searchQuery,
        scope,
        limit: 20,
        category: scope === "clauses" || scope === "precedents" ? category || undefined : undefined,
        risk_level: scope === "clauses" ? riskLevel || undefined : undefined,
      });
      setResults(response.results);
      setMeta({
        collection: response.collection,
        purpose: response.collection_purpose,
        backend: response.backend,
        count: response.count,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageTransition>
      <SectionHeading
        eyebrow="Qdrant"
        title="Semantic search"
        description="Vector search across all four collections. Not keyword matching — a query for 'uncapped exposure' finds clauses that never use those words."
      />

      {/* ── scope picker ── */}
      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SCOPES.map((item) => {
          const Icon = item.icon;
          const active = scope === item.key;
          const stat = scopeStats?.find((s) => s.key === item.key);
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                setScope(item.key);
                setResults(null);
                setMeta(null);
              }}
              className={cn(
                "rounded-xl border p-3.5 text-left transition-all duration-200 ease-premium",
                active
                  ? "border-accent/45 bg-accent/[0.07] shadow-glow-sm"
                  : "border-silver-50/[0.07] bg-base-800/40 hover:border-silver-50/15",
              )}
              aria-pressed={active}
            >
              <div className="flex items-center justify-between">
                <Icon className={cn("size-4", active ? "text-accent" : "text-silver-400")} />
                {stat && (
                  <span className="numeric text-[0.625rem] text-silver-600">
                    {stat.points} pts
                  </span>
                )}
              </div>
              <p
                className={cn(
                  "mt-2.5 text-xs font-semibold",
                  active ? "text-silver-50" : "text-silver-200",
                )}
              >
                {item.label}
              </p>
              <p className="mt-1 text-[0.625rem] leading-relaxed text-silver-500">{item.blurb}</p>
            </button>
          );
        })}
      </div>

      {/* ── query ── */}
      <Card className="mb-5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
          className="space-y-3"
        >
          <div className="flex flex-wrap gap-3">
            <div className="relative min-w-56 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-silver-500" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Describe what you're looking for, in your own words"
                className="pl-9"
                data-testid="search-input"
              />
            </div>
            <Button type="submit" variant="primary" loading={loading} disabled={!query.trim()}>
              <Search className="size-3.5" /> Search
            </Button>
          </div>

          {(scope === "clauses" || scope === "precedents") && (
            <div className="flex flex-wrap gap-3">
              <Select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full sm:w-52"
                aria-label="Filter by category"
              >
                <option value="">All categories</option>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
              {scope === "clauses" && (
                <Select
                  value={riskLevel}
                  onChange={(e) => setRiskLevel(e.target.value)}
                  className="w-full sm:w-44"
                  aria-label="Filter by risk level"
                >
                  <option value="">All risk levels</option>
                  {RISK_LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </Select>
              )}
              <p className="flex items-center text-2xs text-silver-600">
                Filters are applied inside Qdrant, not after — vector search plus a payload
                constraint.
              </p>
            </div>
          )}
        </form>

        {/* examples */}
        {!results && (
          <div className="mt-4 border-t border-silver-50/[0.06] pt-4">
            <p className="eyebrow mb-2.5">Try</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => {
                    setQuery(example);
                    run(example);
                  }}
                  className="rounded-full border border-silver-50/[0.08] bg-base-900/50 px-3 py-1.5 text-2xs text-silver-300 transition-colors hover:border-accent/35 hover:text-accent-soft"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {error && (
        <Alert variant="danger" className="mb-5">
          {error}
        </Alert>
      )}

      {/* ── results ── */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} lines={3} />
          ))}
        </div>
      ) : results === null ? null : results.length === 0 ? (
        <EmptyState
          icon={<Search className="size-5" />}
          title="No matches"
          description="Nothing scored above the similarity threshold. Try broader wording, remove filters, or search a different collection."
        />
      ) : (
        <>
          {meta && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <Badge variant="accent">{meta.count} results</Badge>
              <Badge variant="neutral" size="sm">
                collection: {meta.collection}
              </Badge>
              <Badge variant="neutral" size="sm">
                backend: {meta.backend}
              </Badge>
              <p className="text-2xs text-silver-500">{meta.purpose}</p>
            </div>
          )}

          <Stagger className="space-y-3">
            {results.map((result) => (
              <StaggerItem key={result.id}>
                <ResultCard result={result} scope={scope} />
              </StaggerItem>
            ))}
          </Stagger>
        </>
      )}
    </PageTransition>
  );
}

function ResultCard({ result, scope }: { result: SearchResult; scope: string }) {
  const pct = Math.round((result.score ?? 0) * 100);
  const href =
    scope === "clauses" && result.clause_id
      ? `/clauses/${result.clause_id}`
      : scope === "clauses" && result.contract_id
        ? `/contracts/${result.contract_id}`
        : null;

  const body = (
    <Card hover={!!href} className="h-full">
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <Badge variant="accent" size="sm">
          {pct}% match
        </Badge>
        {result.category && (
          <Badge variant="neutral" size="sm">
            {result.category}
          </Badge>
        )}
        {result.risk_level && <RiskBadge level={result.risk_level} size="sm" />}
        {result.outcome && (
          <Badge
            variant={
              result.outcome === "accepted"
                ? "low"
                : result.outcome === "escalated"
                  ? "high"
                  : "neutral"
            }
            size="sm"
          >
            {String(result.outcome)}
          </Badge>
        )}
        {result.title && (
          <span className="text-2xs font-medium text-silver-200">{String(result.title)}</span>
        )}
        {(result.contract_title || result.heading) && (
          <span className="ml-auto flex items-center gap-1 truncate text-[0.625rem] text-silver-600">
            {truncate(String(result.heading || result.contract_title), 40)}
            {href && <ArrowUpRight className="size-2.5 shrink-0" />}
          </span>
        )}
      </div>

      <p className="whitespace-pre-wrap font-mono text-2xs leading-relaxed text-silver-300">
        {truncate(String(result.text ?? result.guidance ?? result.final_language ?? ""), 420)}
      </p>

      {/* similarity bar */}
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-base-700/60">
        <div className="h-full rounded-full bg-accent/60" style={{ width: `${pct}%` }} />
      </div>
    </Card>
  );

  return href ? (
    <Link href={href} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

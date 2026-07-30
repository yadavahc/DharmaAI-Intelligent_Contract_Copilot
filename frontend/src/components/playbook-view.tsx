"use client";

import {
  BookOpen,
  Database,
  FlaskConical,
  Plus,
  Power,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Collapse, PageTransition, Stagger, StaggerItem } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  Input,
  Label,
  SectionHeading,
  Select,
  SkeletonCard,
  Textarea,
  Tooltip,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { PlaybookRule } from "@/lib/types";
import { cn, severityClasses, titleCase } from "@/lib/utils";

const RULE_TYPE_HELP: Record<string, string> = {
  monetary_threshold: "Compares the largest monetary amount in the clause against a threshold.",
  duration_threshold: "Compares the longest duration (normalised to days) against a threshold.",
  forbidden_language: "Fires when any listed keyword appears in the clause.",
  required_language: "Fires when none of the listed keywords appear. Must target one category.",
};

export function PlaybookView() {
  const [rules, setRules] = React.useState<PlaybookRule[] | null>(null);
  const [meta, setMeta] = React.useState<{
    rule_types: string[];
    operators: string[];
    categories: string[];
    vector_indexed: number;
  } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [testText, setTestText] = React.useState("");
  const [testResult, setTestResult] = React.useState<Awaited<
    ReturnType<typeof api.testRules>
  > | null>(null);

  const load = React.useCallback(async () => {
    try {
      setError(null);
      const response = await api.playbook();
      setRules(response.rules);
      setMeta({
        rule_types: response.rule_types,
        operators: response.operators,
        categories: response.categories,
        vector_indexed: response.vector_indexed,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setRules([]);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const toggleActive = async (rule: PlaybookRule) => {
    try {
      await api.updateRule(rule.id, { active: !rule.active });
      toast.success(`${rule.id} ${rule.active ? "deactivated" : "activated"}`);
      await load();
    } catch (err) {
      toast.error("Update failed", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    }
  };

  const remove = async (rule: PlaybookRule) => {
    if (!window.confirm(`Delete rule ${rule.id}? Clause scoring will change.`)) return;
    try {
      await api.deleteRule(rule.id);
      toast.success(`${rule.id} deleted`);
      await load();
    } catch (err) {
      toast.error("Delete failed", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    }
  };

  const runTest = async () => {
    if (!testText.trim()) return;
    setTesting(true);
    try {
      setTestResult(await api.testRules(testText));
    } catch (err) {
      toast.error("Test failed", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    } finally {
      setTesting(false);
    }
  };

  const grouped = React.useMemo(() => {
    if (!rules) return [];
    const map = new Map<string, PlaybookRule[]>();
    for (const rule of rules) {
      const key = rule.category === "*" ? "All categories" : rule.category;
      map.set(key, [...(map.get(key) ?? []), rule]);
    }
    return [...map.entries()].sort(([a], [b]) =>
      a === "All categories" ? -1 : b === "All categories" ? 1 : a.localeCompare(b),
    );
  }, [rules]);

  return (
    <PageTransition>
      <SectionHeading
        eyebrow="Governance"
        title="Playbook manager"
        description="Admin-defined rules that determine how every clause is scored. Stored in Postgres and embedded into Qdrant so the Risk Agent retrieves only the rules relevant to each clause."
        action={
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setCreating((c) => !c)}>
              {creating ? <X className="size-3.5" /> : <Plus className="size-3.5" />}
              {creating ? "Cancel" : "New rule"}
            </Button>
          </div>
        }
      />

      {error && (
        <Alert variant="danger" className="mb-5">
          {error}
        </Alert>
      )}

      {/* ── stats ── */}
      {rules && meta && (
        <div className="mb-5 flex flex-wrap gap-2">
          <Badge variant="accent">
            <BookOpen className="size-2.5" /> {rules.length} rules
          </Badge>
          <Badge variant="low">{rules.filter((r) => r.active).length} active</Badge>
          <Badge variant="neutral">
            <Database className="size-2.5" /> {meta.vector_indexed} embedded in Qdrant
          </Badge>
        </div>
      )}

      {/* ── create form ── */}
      <Collapse open={creating}>
        {meta && (
          <RuleForm
            meta={meta}
            onCreated={async () => {
              setCreating(false);
              await load();
            }}
          />
        )}
      </Collapse>

      {/* ── rule tester ── */}
      <Card className="mb-6">
        <div className="mb-1 flex items-center gap-2">
          <FlaskConical className="size-3.5 text-accent" />
          <CardTitle>Test the playbook</CardTitle>
        </div>
        <p className="mb-3 text-2xs leading-relaxed text-silver-500">
          Paste any clause text to see exactly which rules fire against it — a dry run, nothing is
          saved.
        </p>
        <Textarea
          value={testText}
          onChange={(e) => setTestText(e.target.value)}
          rows={3}
          placeholder="e.g. Supplier shall have unlimited liability up to $250,000 and Customer shall pay Net 90."
          className="font-mono text-xs"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={runTest}
            loading={testing}
            disabled={!testText.trim()}
          >
            Run test
          </Button>
          {testResult && (
            <>
              <Badge variant="neutral" size="sm">
                classified as {testResult.category}
              </Badge>
              <Badge variant={testResult.compliant ? "low" : "critical"} size="sm">
                {testResult.compliant
                  ? "compliant"
                  : `${testResult.violations.length} breach${testResult.violations.length === 1 ? "" : "es"}`}
              </Badge>
              {!testResult.compliant && (
                <Badge variant="high" size="sm">
                  +{testResult.total_risk_points} risk points
                </Badge>
              )}
              <span className="text-2xs text-silver-600">
                {testResult.rules_evaluated} rules evaluated
              </span>
            </>
          )}
        </div>
        {testResult && testResult.violations.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {testResult.violations.map((v) => (
              <li
                key={v.rule_id}
                className="flex items-start gap-2 rounded-md border border-risk-critical/20 bg-risk-critical/[0.05] p-2.5"
              >
                <code className="shrink-0 font-mono text-[0.625rem] font-bold text-risk-critical">
                  {v.rule_id}
                </code>
                <span className="text-2xs leading-relaxed text-silver-300">{v.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* ── rules ── */}
      {rules === null ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonCard key={i} lines={2} />
          ))}
        </div>
      ) : rules.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="size-5" />}
          title="No playbook rules"
          description="Without rules, risk scoring falls back to language signals only. Reseed the defaults to get 14 starter rules."
        />
      ) : (
        <div className="space-y-8">
          {grouped.map(([category, categoryRules]) => (
            <div key={category}>
              <div className="mb-3 flex items-center gap-2">
                <h3 className="text-sm font-semibold text-silver-100">{category}</h3>
                <Badge variant="neutral" size="sm">
                  {categoryRules.length}
                </Badge>
              </div>
              <Stagger className="space-y-2.5">
                {categoryRules.map((rule) => (
                  <StaggerItem key={rule.id}>
                    <Card
                      className={cn(
                        "transition-opacity",
                        !rule.active && "opacity-55",
                      )}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <code className="font-mono text-2xs font-bold text-accent-soft">
                              {rule.id}
                            </code>
                            <p className="text-sm font-medium text-silver-100">{rule.title}</p>
                          </div>

                          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                            <Tooltip content={RULE_TYPE_HELP[rule.rule_type] ?? ""}>
                              <Badge variant="neutral" size="sm">
                                {titleCase(rule.rule_type)}
                              </Badge>
                            </Tooltip>
                            <Badge
                              size="sm"
                              className={cn("border", severityClasses(rule.severity.toLowerCase()))}
                            >
                              {rule.severity}
                            </Badge>
                            <Badge variant="neutral" size="sm">
                              +{rule.risk_points} pts
                            </Badge>
                            {rule.threshold !== null && (
                              <Badge variant="neutral" size="sm">
                                {rule.operator} {rule.threshold.toLocaleString()}
                              </Badge>
                            )}
                            {!rule.active && (
                              <Badge variant="medium" size="sm">
                                inactive
                              </Badge>
                            )}
                          </div>

                          {rule.keywords.length > 0 && (
                            <p className="mt-2 font-mono text-[0.625rem] leading-relaxed text-silver-500">
                              {rule.keywords.slice(0, 6).map((k) => `"${k}"`).join(" · ")}
                              {rule.keywords.length > 6 && ` +${rule.keywords.length - 6} more`}
                            </p>
                          )}

                          {rule.guidance && (
                            <p className="mt-2 text-2xs leading-relaxed text-silver-400">
                              {rule.guidance}
                            </p>
                          )}

                          {rule.preferred_language && (
                            <details className="mt-2.5 group">
                              <summary className="cursor-pointer text-[0.625rem] font-semibold uppercase tracking-wider text-accent-soft">
                                Preferred language
                              </summary>
                              <p className="mt-1.5 rounded-md border border-silver-50/[0.06] bg-base-900/50 p-2.5 font-mono text-[0.625rem] leading-relaxed text-silver-300">
                                {rule.preferred_language}
                              </p>
                            </details>
                          )}
                        </div>

                        <div className="flex shrink-0 gap-1">
                          <Tooltip content={rule.active ? "Deactivate" : "Activate"}>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              onClick={() => toggleActive(rule)}
                              aria-label={rule.active ? "Deactivate rule" : "Activate rule"}
                            >
                              <Power
                                className={cn(
                                  "size-3.5",
                                  rule.active ? "text-risk-low" : "text-silver-500",
                                )}
                              />
                            </Button>
                          </Tooltip>
                          <Tooltip content="Delete rule">
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              onClick={() => remove(rule)}
                              aria-label="Delete rule"
                            >
                              <Trash2 className="size-3.5 text-risk-critical" />
                            </Button>
                          </Tooltip>
                        </div>
                      </div>
                    </Card>
                  </StaggerItem>
                ))}
              </Stagger>
            </div>
          ))}
        </div>
      )}
    </PageTransition>
  );
}

/* ── create form ────────────────────────────────────────────────────────── */

function RuleForm({
  meta,
  onCreated,
}: {
  meta: { rule_types: string[]; operators: string[]; categories: string[] };
  onCreated: () => void;
}) {
  const [form, setForm] = React.useState({
    title: "",
    category: "Liability",
    rule_type: "forbidden_language",
    operator: "",
    threshold: "",
    keywords: "",
    severity: "Medium",
    risk_points: 20,
    guidance: "",
    preferred_language: "",
  });
  const [saving, setSaving] = React.useState(false);

  const needsThreshold =
    form.rule_type === "monetary_threshold" || form.rule_type === "duration_threshold";
  const needsKeywords =
    form.rule_type === "forbidden_language" || form.rule_type === "required_language";
  const wildcardRequired = form.rule_type === "required_language" && form.category === "*";

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.createRule({
        title: form.title,
        category: form.category,
        rule_type: form.rule_type as PlaybookRule["rule_type"],
        operator: needsThreshold ? form.operator || "gt" : "",
        threshold: needsThreshold && form.threshold ? Number(form.threshold) : null,
        keywords: needsKeywords
          ? form.keywords.split(",").map((k) => k.trim()).filter(Boolean)
          : [],
        severity: form.severity,
        risk_points: Number(form.risk_points),
        guidance: form.guidance,
        preferred_language: form.preferred_language,
        active: true,
      });
      toast.success("Rule created", {
        description: "It is now embedded in Qdrant and will apply to the next review.",
      });
      onCreated();
    } catch (err) {
      toast.error("Could not create the rule", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="mb-6 border-accent/20">
      <CardTitle className="mb-4">New playbook rule</CardTitle>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <Label htmlFor="rule-title">Title</Label>
          <Input
            id="rule-title"
            required
            minLength={3}
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Liability exposure above $100,000 is High Risk"
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <Label htmlFor="rule-category">Category</Label>
            <Select
              id="rule-category"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              {meta.categories.map((c) => (
                <option key={c} value={c}>
                  {c === "*" ? "All categories" : c}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="rule-type">Rule type</Label>
            <Select
              id="rule-type"
              value={form.rule_type}
              onChange={(e) => setForm({ ...form, rule_type: e.target.value })}
            >
              {meta.rule_types.map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="rule-severity">Severity</Label>
            <Select
              id="rule-severity"
              value={form.severity}
              onChange={(e) => setForm({ ...form, severity: e.target.value })}
            >
              {["Low", "Medium", "High"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <p className="text-2xs leading-relaxed text-silver-500">
          {RULE_TYPE_HELP[form.rule_type]}
        </p>

        {wildcardRequired && (
          <Alert variant="warning" title="Not allowed">
            A required-language rule must target a specific category. Applied to all categories it
            would fire on every clause that is not about its subject, inflating the whole
            contract&apos;s score. The backend rejects this combination.
          </Alert>
        )}

        {needsThreshold && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="rule-operator">Operator</Label>
              <Select
                id="rule-operator"
                value={form.operator}
                onChange={(e) => setForm({ ...form, operator: e.target.value })}
              >
                <option value="">Select…</option>
                {meta.operators.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="rule-threshold">
                Threshold {form.rule_type === "duration_threshold" ? "(days)" : "(amount)"}
              </Label>
              <Input
                id="rule-threshold"
                type="number"
                value={form.threshold}
                onChange={(e) => setForm({ ...form, threshold: e.target.value })}
                placeholder={form.rule_type === "duration_threshold" ? "180" : "100000"}
              />
            </div>
          </div>
        )}

        {needsKeywords && (
          <div>
            <Label htmlFor="rule-keywords">Keywords (comma-separated)</Label>
            <Input
              id="rule-keywords"
              value={form.keywords}
              onChange={(e) => setForm({ ...form, keywords: e.target.value })}
              placeholder="unlimited liability, no cap on liability"
            />
          </div>
        )}

        <div>
          <Label htmlFor="rule-points">Risk points added when it fires</Label>
          <Input
            id="rule-points"
            type="number"
            min={0}
            max={100}
            value={form.risk_points}
            onChange={(e) => setForm({ ...form, risk_points: Number(e.target.value) })}
          />
        </div>

        <div>
          <Label htmlFor="rule-guidance">Guidance for the agents</Label>
          <Textarea
            id="rule-guidance"
            rows={2}
            value={form.guidance}
            onChange={(e) => setForm({ ...form, guidance: e.target.value })}
            placeholder="Aggregate liability must be capped at twelve months of fees."
          />
        </div>

        <div>
          <Label htmlFor="rule-language">Preferred contract language (optional)</Label>
          <Textarea
            id="rule-language"
            rows={3}
            value={form.preferred_language}
            onChange={(e) => setForm({ ...form, preferred_language: e.target.value })}
            placeholder="Each party's aggregate liability shall not exceed…"
            className="font-mono text-xs"
          />
        </div>

        <Button type="submit" variant="primary" loading={saving} disabled={wildcardRequired}>
          <Plus className="size-4" /> Create rule
        </Button>
      </form>
    </Card>
  );
}

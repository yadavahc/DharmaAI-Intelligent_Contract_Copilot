/**
 * Typed client for the FastAPI backend.
 *
 * Browser requests go through the Next.js proxy at `/api/proxy/*` rather than
 * straight to the backend. That gives one origin (no CORS preflight on every
 * call), lets the server attach the authenticated actor identity and role so the
 * client cannot spoof them, and keeps the backend URL out of the client bundle.
 *
 * `streamSSE` exists because `EventSource` cannot issue POST requests, and both
 * of our streams (contract review, negotiation) are POSTs.
 */

import type {
  AgentCard,
  AuditEvent,
  ChainVerification,
  Clause,
  ClauseVersion,
  Coaching,
  Contract,
  DashboardData,
  ExecutiveSummary,
  GuardrailVerdict,
  HealthResponse,
  LyzrPipelineDemo,
  LyzrRuntime,
  Negotiation,
  NegotiationEvent,
  PlaybookRule,
  Precedent,
  ReviewEvent,
  ReviewTask,
  SearchResult,
  SimulationResult,
} from "@/lib/types";

/** Server-side: talk to the backend directly. Client-side: use the proxy. */
export const API_BASE =
  typeof window === "undefined"
    ? process.env.API_INTERNAL_URL ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      "http://localhost:8000"
    : "/api/proxy";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Bypass Next's fetch cache; most of our reads are live data. */
  noStore?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, noStore = true, headers, ...rest } = options;

  const init: RequestInit = {
    ...rest,
    headers: {
      ...(body !== undefined && !(body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(headers as Record<string, string>),
    },
    ...(noStore ? { cache: "no-store" as RequestCache } : {}),
  };

  if (body !== undefined) {
    init.body = body instanceof FormData ? body : JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (cause) {
    // A network-level failure is the most common demo-day problem; say so
    // clearly rather than surfacing "Failed to fetch".
    throw new ApiError(
      `Cannot reach the Dharma AI backend. Is it running? (${String(cause)})`,
      0,
      cause,
    );
  }

  if (!response.ok) {
    let detail: unknown;
    let message = `Request failed (${response.status})`;
    try {
      detail = await response.json();
      const d = (detail as { detail?: unknown }).detail;
      if (typeof d === "string") message = d;
      else if (Array.isArray(d) && d.length) {
        // FastAPI validation errors arrive as an array of issues.
        const first = d[0] as { loc?: string[]; msg?: string };
        message = `${first.loc?.slice(-1)[0] ?? "input"}: ${first.msg ?? "invalid"}`;
      }
    } catch {
      message = `${message}: ${response.statusText}`;
    }
    throw new ApiError(message, response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/* ──────────────────────────────────────────────────────────────────────────
 * SSE over POST
 * ────────────────────────────────────────────────────────────────────────── */

export interface StreamHandlers<E> {
  onEvent: (event: E) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
  signal?: AbortSignal;
}

/**
 * Read a `text/event-stream` response produced by a POST.
 *
 * Buffers by `\n\n` frame boundaries: a chunk can split a frame mid-JSON, and
 * parsing eagerly would drop events. Ignores abort errors, which are the normal
 * result of the user navigating away.
 */
export async function streamSSE<E>(
  path: string,
  { onEvent, onError, onDone, signal }: StreamHandlers<E>,
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { Accept: "text/event-stream" },
      signal,
      cache: "no-store",
    });

    if (!response.ok || !response.body) {
      throw new ApiError(
        `Stream failed (${response.status} ${response.statusText})`,
        response.status,
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        for (const line of frame.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (!payload) continue;
          try {
            onEvent(JSON.parse(payload) as E);
          } catch {
            // A malformed frame should not kill the stream.
          }
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
    onDone?.();
  } catch (error) {
    if ((error as Error)?.name === "AbortError") {
      onDone?.();
      return;
    }
    onError?.(error as Error);
  }
}

/* ──────────────────────────────────────────────────────────────────────────
 * API surface
 * ────────────────────────────────────────────────────────────────────────── */

export const api = {
  // ── system ──
  health: () => request<HealthResponse>("/api/health"),
  agents: () =>
    request<{ runtime: LyzrRuntime; count: number; agents: AgentCard[] }>("/api/agents"),
  lyzrRuntime: () => request<LyzrRuntime>("/api/agents/runtime"),
  telemetry: (limit = 40) =>
    request<{
      summary: DashboardData["agent_telemetry"];
      recent_calls: Record<string, unknown>[];
    }>(`/api/agents/telemetry?limit=${limit}`),
  lyzrPipelineDemo: (clauseText?: string, heading?: string) => {
    const params = new URLSearchParams();
    if (clauseText) params.set("clause_text", clauseText);
    if (heading) params.set("heading", heading);
    const qs = params.toString();
    return request<LyzrPipelineDemo>(
      `/api/agents/pipeline/demo${qs ? `?${qs}` : ""}`,
      { method: "POST" },
    );
  },
  vectorHealth: () =>
    request<{ store: HealthResponse["vector_store"]; collection_purposes: Record<string, string> }>(
      "/api/vector/health",
    ),
  demoReset: (loadSample = false) =>
    request<{ reset: boolean; sample_contract_id?: string; sample_clause_count?: number }>(
      `/api/demo/reset?include_vectors=true&load_sample=${loadSample}`,
      { method: "POST" },
    ),
  demoSeed: () => request<Record<string, unknown>>("/api/demo/seed", { method: "POST" }),

  // ── contracts ──
  contracts: (params: { limit?: number; offset?: number; status?: string; risk_level?: string } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    return request<{ total: number; limit: number; offset: number; contracts: Contract[] }>(
      `/api/contracts${qs ? `?${qs}` : ""}`,
    );
  },
  contract: (id: string, includeText = false) =>
    request<Contract>(`/api/contracts/${id}?include_text=${includeText}`),
  dashboard: () => request<DashboardData>("/api/contracts/dashboard"),
  uploadContract: (form: FormData) =>
    request<{
      contract_id: string;
      title: string;
      status: string;
      clause_count: number;
      blocked: boolean;
      guardrails: { summary: string; verdicts: GuardrailVerdict[]; blocked: boolean; requires_review: boolean };
    }>("/api/contracts/upload", { method: "POST", body: form }),
  loadSampleContract: () =>
    request<{ contract_id: string; title: string; clause_count: number }>(
      "/api/contracts/sample",
      { method: "POST" },
    ),
  supportedTypes: () => request<{ extensions: string[]; max_mb: number }>("/api/contracts/supported-types"),
  reviewContract: (id: string) =>
    request<{ contract_id: string; risk: SimulationResult["contract"]["before"]; escalated: number }>(
      `/api/contracts/${id}/review`,
      { method: "POST" },
    ),
  streamReview: (id: string, handlers: StreamHandlers<ReviewEvent>) =>
    streamSSE<ReviewEvent>(`/api/contracts/${id}/review/stream`, handlers),
  executiveSummary: (id: string, refresh = false) =>
    request<ExecutiveSummary & { contract_id: string }>(
      `/api/contracts/${id}/executive-summary?refresh=${refresh}`,
      { method: "POST" },
    ),
  deleteContract: (id: string) =>
    request<{ deleted: boolean }>(`/api/contracts/${id}`, { method: "DELETE" }),

  // ── clauses ──
  clause: (id: string) => request<Clause>(`/api/clauses/${id}`),
  clauseVersions: (id: string) =>
    request<{ clause_id: string; current_version: number; current_text: string; versions: ClauseVersion[] }>(
      `/api/clauses/${id}/versions`,
    ),
  rollbackClause: (id: string, versionNo: number, reason: string) =>
    request<{ clause_id: string; restored_version: number; current_version: number; text: string }>(
      `/api/clauses/${id}/rollback`,
      { method: "POST", body: { version_no: versionNo, reason } },
    ),
  simulateClause: (clauseText: string, category?: string) =>
    request<{
      category: string;
      risk_score: number;
      risk_level: string;
      rationale: string;
      findings: { code: string; detail: string; points: number; source: string }[];
      triggered_rule_ids: string[];
    }>("/api/clauses/simulate", { method: "POST", body: { clause_text: clauseText, category } }),
  simulateContract: (contractId: string, clauseId: string, clauseText: string) =>
    request<SimulationResult>(`/api/clauses/simulate/contract/${contractId}`, {
      method: "POST",
      body: { clause_id: clauseId, clause_text: clauseText },
    }),
  clausePrecedents: (id: string, limit = 3) =>
    request<{ clause_id: string; category: string; count: number; precedents: Precedent[]; note: string }>(
      `/api/clauses/${id}/precedents?limit=${limit}`,
    ),
  similarClauses: (id: string, limit = 5) =>
    request<{ clause_id: string; category: string; count: number; similar_clauses: SearchResult[] }>(
      `/api/clauses/${id}/similar?limit=${limit}`,
    ),
  categories: () => request<{ categories: string[] }>("/api/clauses/categories"),

  // ── negotiation ──
  streamNegotiation: (
    clauseId: string,
    options: { maxRounds?: number; includeCoach?: boolean },
    handlers: StreamHandlers<NegotiationEvent>,
  ) => {
    const params = new URLSearchParams({ clause_id: clauseId });
    if (options.maxRounds) params.set("max_rounds", String(options.maxRounds));
    if (options.includeCoach !== undefined)
      params.set("include_coach", String(options.includeCoach));
    return streamSSE<NegotiationEvent>(`/api/negotiations/stream?${params}`, handlers);
  },
  runNegotiation: (clauseId: string, maxRounds?: number) => {
    const params = new URLSearchParams({ clause_id: clauseId });
    if (maxRounds) params.set("max_rounds", String(maxRounds));
    return request<{
      negotiation_id: string;
      outcome: string;
      turns: unknown[];
      summary: Record<string, unknown>;
    }>(`/api/negotiations/run?${params}`, { method: "POST" });
  },
  negotiations: (params: { contract_id?: string; outcome?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    return request<{ count: number; negotiations: Negotiation[] }>(
      `/api/negotiations${qs ? `?${qs}` : ""}`,
    );
  },
  negotiation: (id: string) => request<Negotiation>(`/api/negotiations/${id}`),
  coach: (payload: {
    clause_text: string;
    category: string;
    round: number;
    proposed_redline?: string;
    current_risk?: number;
    history?: unknown[];
  }) => request<Coaching>("/api/negotiations/coach", { method: "POST", body: payload }),

  // ── playbook ──
  playbook: (params: { category?: string; active_only?: boolean } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    return request<{
      count: number;
      rules: PlaybookRule[];
      rule_types: string[];
      operators: string[];
      categories: string[];
      vector_indexed: number;
    }>(`/api/playbook${qs ? `?${qs}` : ""}`);
  },
  createRule: (rule: Partial<PlaybookRule>) =>
    request<PlaybookRule & { created: boolean }>("/api/playbook", { method: "POST", body: rule }),
  updateRule: (id: string, changes: Partial<PlaybookRule>) =>
    request<PlaybookRule & { updated: boolean }>(`/api/playbook/${id}`, {
      method: "PATCH",
      body: changes,
    }),
  deleteRule: (id: string) =>
    request<{ deleted: boolean }>(`/api/playbook/${id}`, { method: "DELETE" }),
  testRules: (clauseText: string, category?: string) => {
    const params = new URLSearchParams({ clause_text: clauseText });
    if (category) params.set("category", category);
    return request<{
      category: string;
      rules_evaluated: number;
      violations: { rule_id: string; detail: string; points: number }[];
      compliant: boolean;
      total_risk_points: number;
    }>(`/api/playbook/test?${params}`, { method: "POST" });
  },

  // ── review queue / approval gate ──
  reviewQueue: (params: { status?: string; priority?: string; contract_id?: string } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    return request<{ count: number; counts_by_status: Record<string, number>; tasks: ReviewTask[] }>(
      `/api/review/queue${qs ? `?${qs}` : ""}`,
    );
  },
  reviewTask: (id: string) => request<Record<string, unknown>>(`/api/review/queue/${id}`),
  decide: (
    taskId: string,
    payload: { decision: string; note?: string; edited_text?: string },
  ) =>
    request<{
      task_id: string;
      clause_id: string;
      decision: string;
      previous_state: string;
      approval_state: string;
      finalized: boolean;
    }>(`/api/review/queue/${taskId}/decide`, { method: "POST", body: payload }),
  gateStatus: (clauseId: string) =>
    request<{
      clause_id: string;
      state: string;
      finalized: boolean;
      blocks_finalisation: boolean;
      allowed_transitions: string[];
      authorized_roles: string[];
      gate_report: Record<string, unknown>;
    }>(`/api/review/gate/${clauseId}`),

  // ── audit ──
  audit: (params: { limit?: number; offset?: number; contract_id?: string; actor_type?: string; event_type?: string } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    return request<{ total: number; limit: number; offset: number; events: AuditEvent[] }>(
      `/api/audit${qs ? `?${qs}` : ""}`,
    );
  },
  verifyAudit: () => request<ChainVerification>("/api/audit/verify"),
  auditStats: () =>
    request<{
      total_events: number;
      by_actor_type: Record<string, number>;
      by_event_type: Record<string, number>;
    }>("/api/audit/stats"),

  // ── search ──
  search: (payload: {
    query: string;
    limit?: number;
    category?: string;
    contract_id?: string;
    risk_level?: string;
    scope?: string;
  }) =>
    request<{
      query: string;
      scope: string;
      collection: string;
      collection_purpose: string;
      count: number;
      results: SearchResult[];
      backend: string;
    }>("/api/search", { method: "POST", body: payload }),
  searchScopes: () =>
    request<{
      scopes: { key: string; collection: string; purpose: string; points: number }[];
      backend: string;
    }>("/api/search/scopes"),

  // ── guardrails ──
  guardrailInfo: () =>
    request<{ guardrails: Record<string, unknown>[] }>("/api/guardrails/info"),
  guardrailSamples: () =>
    request<{ samples: Record<string, unknown>[] }>("/api/guardrails/samples"),
  testGuardrail: (payload: {
    text?: string;
    guardrail?: string;
    agent_output?: Record<string, unknown>;
    source_text?: string;
  }) =>
    request<{
      guardrail: string;
      verdicts: GuardrailVerdict[];
      triggered_count: number;
      blocked: boolean;
      requires_approval: boolean;
      sanitized_text?: string;
      sanitized_spans?: number;
      redacted_text?: string;
      redacted_items?: number;
    }>("/api/guardrails/test", { method: "POST", body: payload }),
  testApprovalGate: (payload: Record<string, unknown>) =>
    request<{
      verdict: GuardrailVerdict;
      attempt_allowed?: boolean;
      attempt_error?: string;
      attempt_result?: Record<string, unknown>;
    }>("/api/guardrails/test/approval-gate", { method: "POST", body: payload }),
};

/**
 * Types mirroring the FastAPI response shapes.
 *
 * Hand-written rather than generated: the backend is the source of truth, and a
 * small explicit surface here is easier to read than a generated blob. Fields the
 * UI does not consume are typed loosely on purpose.
 */

export type RiskLevel = "Low" | "Medium" | "High" | "Critical";
export type UserRole = "ADMIN" | "REVIEWER" | "BUSINESS_USER";
export type NegotiationOutcome = "pending" | "accepted" | "rejected" | "escalated";
export type NegotiationSide = "organization" | "counterparty";
export type ApprovalState =
  | "pending_human_approval"
  | "approved"
  | "rejected"
  | "edited_and_approved"
  | "finalized";

export interface AgentCard {
  key: string;
  name: string;
  role: string;
  persona: string;
  instructions: string;
  outputs: string;
  hands_off_to: string[];
  uses_qdrant: boolean;
  qdrant_purpose: string | null;
}

export interface LyzrRuntime {
  lyzr_runtime: "lyzr-automata" | "shim";
  lyzr_version: string | null;
  is_genuine_sdk: boolean;
  import_error: string | null;
  agent_class: string;
  task_class: string;
  pipeline_class: string;
  ai_model_abc: string;
}

export interface HealthResponse {
  status: string;
  demo_mode: boolean;
  openai_key_present: boolean;
  model: string;
  database: { backend: string; connected: boolean; error: string | null };
  vector_store: {
    backend: string;
    embedding_dim: number;
    embedding_method: string;
    collections: Record<string, { points: number; purpose: string }>;
  };
  lyzr: LyzrRuntime;
  thresholds: {
    risk_high: number;
    risk_medium: number;
    negotiation_max_rounds: number;
  };
}

export interface GuardrailFinding {
  rule: string;
  severity: "low" | "medium" | "high" | "critical";
  excerpt: string;
  position: number;
  note: string;
}

export interface GuardrailVerdict {
  guardrail: string;
  triggered: boolean;
  action: "allow" | "flag" | "sanitize" | "block" | "require_approval";
  severity: string;
  summary: string;
  findings: GuardrailFinding[];
  details: Record<string, unknown>;
}

export interface Redline {
  original?: string;
  suggested?: string;
  reason?: string;
  change_summary?: string;
  materiality?: "low" | "medium" | "high";
  confidence?: number;
  unchanged?: boolean;
  used_precedent?: boolean;
  precedent_count?: number;
  precedents?: Precedent[];
  method?: string;
}

export interface PlaybookViolation {
  rule_id: string;
  detail: string;
  severity: string;
  source?: string;
}

export interface ClausePlaybook {
  compliant: boolean;
  violations: PlaybookViolation[];
  matched_rule_ids: string[];
  assessment: string;
  confidence: number;
}

export interface Escalation {
  should_escalate: boolean;
  priority: "low" | "medium" | "high";
  assigned_role: string | null;
  reason: string;
  policy_reasons?: string[];
  recommended_action: string;
  sla_hours: number | null;
  confidence: number;
  forced_by_policy?: boolean;
}

export interface AgentTraceEntry {
  agent: string;
  duration_ms: number;
  confidence?: number | null;
}

export interface Clause {
  id: string;
  contract_id: string;
  index: number;
  label: string;
  heading: string;
  text: string;
  category: string;
  confidence: number;
  risk_score: number;
  risk_level: RiskLevel;
  explanation: string;
  suggested_fix: string;
  redline: Redline;
  playbook: ClausePlaybook | Record<string, never>;
  escalation: Escalation | Record<string, never>;
  guardrails: Record<string, { verdicts?: GuardrailVerdict[]; requires_approval?: boolean }>;
  agent_trace: AgentTraceEntry[];
  approval_state: ApprovalState;
  current_version: number;
  classification?: Record<string, unknown>;
  risk?: Record<string, unknown>;
  versions?: ClauseVersion[];
  contract_title?: string;
}

export interface ClauseVersion {
  id?: string;
  version_no: number;
  text: string;
  source: "original" | "ai_redline" | "negotiation" | "human_edit" | "rollback";
  author: string;
  author_role?: string;
  reason: string;
  risk_score?: number;
  risk_level?: string;
  created_at: string | null;
}

export interface RiskSummary {
  score: number;
  level: RiskLevel;
  clause_count: number;
  weighted_mean: number;
  severity_penalty: number;
  distribution: Record<RiskLevel, number>;
}

export interface Contract {
  id: string;
  title: string;
  filename: string;
  status: string;
  counterparty: string;
  uploaded_by: string;
  clause_count: number;
  page_count: number;
  char_count: number;
  risk_score: number;
  risk_level: RiskLevel;
  risk_summary: RiskSummary | Record<string, never>;
  has_executive_summary: boolean;
  guardrails_flagged: boolean;
  created_at: string | null;
  updated_at: string | null;
  clauses?: Clause[];
  parsed_metadata?: Record<string, unknown>;
  guardrail_report?: {
    verdicts: GuardrailVerdict[];
    blocked: boolean;
    requires_review: boolean;
    summary: string;
    sanitized_spans: number;
  };
  executive_summary?: ExecutiveSummary;
}

export interface ExecutiveSummary {
  headline: string;
  key_obligations: string[];
  financial_exposure: { headline_figure: string; notes: string };
  deadlines: string[];
  renewal_terms: string;
  top_risks: { clause: string; risk: string; why: string }[];
  recommended_actions: string[];
  overall_recommendation: string;
  confidence: number;
  cached?: boolean;
}

export interface DashboardData {
  kpis: {
    contracts: number;
    clauses: number;
    open_reviews: number;
    avg_confidence: number;
    avg_contract_risk: number;
    high_risk_clauses: number;
  };
  risk_distribution: Record<RiskLevel, number>;
  category_distribution: Record<string, number>;
  negotiation_status: Record<string, number>;
  review_by_priority: Record<string, number>;
  confidence_buckets: Record<string, number>;
  recent_contracts: Contract[];
  top_risk_clauses: {
    id: string;
    contract_id: string;
    heading: string;
    category: string;
    risk_score: number;
    risk_level: RiskLevel;
    explanation: string;
  }[];
  recent_activity: AuditEvent[];
  agent_telemetry: {
    total_calls: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    avg_duration_ms: number;
    errors: number;
    by_agent: Record<string, number>;
  };
}

export interface AuditEvent {
  id: string;
  seq: number;
  timestamp: string | null;
  actor_type: "ai_agent" | "human" | "system";
  actor_id: string;
  actor_role: string;
  event_type: string;
  object_type: string;
  object_id: string;
  contract_id: string;
  summary: string;
  compliance_note: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface ChainVerification {
  valid: boolean;
  entries_checked: number;
  problems: { seq: number; issue: string; detail: string }[];
  head_hash: string;
  algorithm: string;
  verified_at: string;
}

export interface PlaybookRule {
  id: string;
  title: string;
  category: string;
  rule_type:
    | "monetary_threshold"
    | "duration_threshold"
    | "forbidden_language"
    | "required_language";
  operator: string;
  threshold: number | null;
  keywords: string[];
  severity: string;
  risk_points: number;
  guidance: string;
  preferred_language: string;
  active: boolean;
}

export interface ReviewTask {
  id: string;
  contract_id: string;
  contract_title: string;
  clause_id: string;
  clause_heading: string;
  clause_text: string;
  category: string;
  priority: "low" | "medium" | "high";
  reason: string;
  recommended_action: string;
  assigned_role: string;
  risk_score: number;
  risk_level: RiskLevel;
  sla_hours: number | null;
  status: string;
  decision: string;
  decision_note: string;
  decided_by: string;
  decided_at: string | null;
  approval_state: ApprovalState | null;
  redline: Redline;
  created_at: string | null;
}

export interface NegotiationTurn {
  round: number;
  side: NegotiationSide;
  agent_role: string;
  message: string;
  stance: "counter" | "accept" | "reject" | "escalate";
  proposed_language: string;
  concession: string;
  rationale: string;
  projected_risk_score: number;
  confidence: number;
  coaching?: Coaching;
  created_at?: string | null;
}

export interface Coaching {
  acceptance_probability: number;
  recommended_move: string;
  leverage_assessment: string;
  risks_of_pushing: string;
  walk_away_signal: boolean;
  confidence: number;
  round?: number;
}

export interface Negotiation {
  id: string;
  contract_id: string;
  clause_id: string;
  clause_heading?: string;
  clause_text?: string;
  category: string;
  outcome: NegotiationOutcome;
  rounds_used: number;
  max_rounds: number;
  initial_risk: number;
  final_risk: number;
  risk_reduction?: number;
  final_language?: string;
  escalated: boolean;
  summary?: Record<string, unknown>;
  turns?: NegotiationTurn[];
  created_at: string | null;
  completed_at?: string | null;
}

/** Discriminated union of SSE events from the negotiation stream. */
export type NegotiationEvent =
  | { type: "meta"; negotiation_id: string; clause_id: string; clause_heading: string; contract_id: string; contract_title: string; category: string; memory_hits: number; playbook_rule_ids: string[] }
  | { type: "start"; category: string; max_rounds: number; initial_risk_score: number; clause_preview: string; agents: Record<NegotiationSide, { role: string; persona: string }> }
  | { type: "thinking"; round: number; side: NegotiationSide; agent_role: string }
  | ({ type: "turn" } & NegotiationTurn)
  | { type: "risk"; round: number; risk_score: number; delta: number }
  | ({ type: "coach"; round: number } & Coaching)
  | { type: "outcome"; outcome: NegotiationOutcome; round: number; reason: string }
  | ({ type: "escalation" } & Escalation)
  | { type: "done"; outcome: NegotiationOutcome; rounds_used: number; final_risk_score: number; initial_risk_score: number; risk_reduction: number; final_language: string; requires_human_approval: boolean; escalated: boolean; turn_count: number }
  | { type: "persisted"; negotiation_id: string }
  | { type: "error"; error: string }
  | { type: "stream_end"; negotiation_id?: string };

/** SSE events from the contract review stream. */
export type ReviewEvent =
  | { type: "start"; contract_id: string; title: string; clause_count: number }
  | { type: "clause_started"; clause_id: string; index: number; heading: string }
  | { type: "clause_done"; clause_id: string; index: number; heading: string; category: string; confidence: number; risk_score: number; risk_level: RiskLevel; explanation: string; escalated: boolean; precedent_count: number; progress: { done: number; total: number; pct: number } }
  | { type: "contract_done"; contract_id: string; risk: RiskSummary; clauses_reviewed: number; escalated: number; review_tasks_created: number }
  | { type: "error"; error: string; clause_id?: string }
  | { type: "stream_end" };

export interface Precedent {
  id: string;
  score: number;
  similarity_pct?: number;
  category: string;
  contract_title: string;
  contract_id: string;
  clause_id: string;
  approved_by: string;
  risk_level: string;
  notes: string;
  text: string;
}

export interface SearchResult {
  id: string;
  score: number;
  text?: string;
  category?: string;
  heading?: string;
  contract_id?: string;
  contract_title?: string;
  clause_id?: string;
  risk_level?: string;
  risk_score?: number;
  title?: string;
  outcome?: string;
  [key: string]: unknown;
}

export interface SimulationResult {
  contract_id: string;
  clause_id: string;
  category: string;
  clause: {
    before: { score: number; level: string };
    after: { score: number; level: string };
    delta: number;
    rationale: string;
    findings: { code: string; detail: string; points: number; source: string }[];
  };
  contract: {
    before: RiskSummary;
    after: RiskSummary;
    delta: number;
  };
  method: string;
}

export interface LyzrPipelineDemo {
  pipeline_name: string;
  pipeline_class: string;
  runtime: LyzrRuntime;
  duration_ms: number;
  task_count: number;
  tasks: {
    task_name: string;
    task_id: string;
    agent_role: string;
    agent_persona: string;
    instructions: string;
    input_tasks: string[];
    output_parsed: unknown;
    output_raw: string;
  }[];
}

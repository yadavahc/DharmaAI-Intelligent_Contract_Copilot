# The Lyzr Agent Flow

Every LLM call in Dharma AI is made by a Lyzr agent. This document lists each
agent, what it does, and how they hand off — plus exactly how the framework is
wired, because that is the part worth verifying rather than taking on trust.

**Verify it yourself, from the running service:**

```bash
curl localhost:8000/api/agents/runtime   # which runtime is live, which classes are bound
curl localhost:8000/api/agents           # all 11 agents with role, persona, instructions
curl -X POST localhost:8000/api/agents/pipeline/demo   # runs a real LinearSyncPipeline
```

Or open **Settings** in the app, which renders all three.

---

## 1. How Lyzr is wired

### What the SDK actually provides

`lyzr-automata==0.1.3` exposes a small, clean surface (read from the installed
wheel, not from documentation):

| Class | Signature |
| --- | --- |
| `Agent` | `Agent(role: str, memory=None, prompt_persona: str = "")` |
| `Task` | `Task(model, instructions, default_input, name, log_output, output_type, agent, input_type, tool, file_paths, previous_output, resource_box, input_tasks, enhance_prompt, logger)` → `.execute() -> str` |
| `LinearSyncPipeline` | `LinearSyncPipeline(tasks, completion_message, name, resource_box, logger)` → `.run() -> list[{"task_id", "task_output"}]` |
| `AIModel` (ABC) | `generate_text(task_id, system_persona, prompt, ...)`, `generate_image(...)` |

Lyzr assembles each prompt from the agent and task like this:

```
system := f"In your role as {agent.role}, you embody a persona defined by {agent.prompt_persona}."
user   := f"Now execute these instructions: {task.instructions}.  Input: {previous_output} {default_input}"
```

That assembly is why `role` and `prompt_persona` are load-bearing rather than
decorative — they are injected into every single call.

### Where Dharma AI plugs in

`Task` accepts **any** `AIModel`, so implementing that one ABC is the supported
way to extend the framework. Dharma AI supplies
[`DharmaOpenAIModel`](../backend/app/agents/model.py) instead of the SDK's bundled
`OpenAIModel`, for three reasons:

1. **Structured output.** Classification, risk scores and redlines are consumed as
   typed JSON. The bundled model is text-only.
2. **Streaming.** The Live Agent Theater renders negotiation tokens as they
   arrive; `generate_text` alone cannot express that.
3. **Dependency hygiene.** The bundled model pins `openai==1.3.4`. We use the
   modern SDK.

The neat part: Lyzr spreads a model's `parameters` dict straight into
`chat.completions.create(**parameters, messages=...)`. Putting
`response_format={"type": "json_object"}` in `parameters` means **a plain
`Task.execute()` returns strict JSON** — so structured agents run through genuine
Lyzr task execution rather than around it. There is no "real Lyzr path" and
separate shortcut path.

Per-agent model instances also carry the agent's role, which restores audit
attribution that `Task` would otherwise drop (it calls `generate_text` with no
metadata argument).

### The `--no-deps` install, and why

`lyzr-automata` declares two hard pins:

```
openai==1.3.4      requests==2.31.0
```

The `openai` pin exists solely for `lyzr_automata.ai_models.openai.OpenAIModel` —
the class we replace. The import chain Dharma AI actually exercises is:

```
lyzr_automata/__init__.py
  ├── agents/agent_base.py                (stdlib only)
  ├── tasks/task_base.py                  (stdlib + lyzr internals)
  ├── tools/tool_base.py                  (stdlib + lyzr internals)
  ├── pipelines/linear_sync_pipeline.py   (stdlib + lyzr internals)
  ├── logger.py                           (requests)
  ├── utils/resource_handler.py           (requests)
  └── data_models.py                      (pydantic)
```

`ai_models/openai.py` is **never imported**, so `openai==1.3.4` is never needed.
Hence:

```bash
pip install -r requirements.txt
pip install --no-deps -r requirements-lyzr.txt
```

The Docker image uses `python:3.11-slim`, which satisfies the wheel's declared
`Requires-Python: >=3.8.1,<3.12` natively, and the build **fails loudly** if the
genuine SDK does not import — so an image can't silently ship on the fallback.

For local venvs on newer Pythons, add `--ignore-requires-python`. The cap is
conservative metadata on a pure-Python `py3-none-any` wheel; it imports and runs
correctly on 3.12–3.14 (verified).

### The fallback, and how to tell

If `lyzr-automata` cannot be imported at all,
[`lyzr_compat.py`](../backend/app/agents/lyzr_compat.py) supplies a
signature-identical shim — including Lyzr's exact prompt assembly and its
`input_tasks` chaining rule, so model output does not change. `LYZR_RUNTIME` flips
to `"shim"` and `GET /api/agents/runtime` reports
`is_genuine_sdk: false`, the app header shows it, and Settings shows a warning.
The claim is always checkable rather than assumed.

---

## 2. The agents

Nine required agents, plus two supporting the signature features.

### Ingest agents

#### 1. Contract Parsing Agent
- **Role:** `Contract Parsing Specialist`
- **Persona:** A meticulous contracts paralegal who reads structurally and never invents a fact.
- **Input:** Raw extracted document text.
- **Output:** `title`, `parties[]`, `effective_date`, `governing_law`, `term`, `document_type`, `confidence`
- **Hands off to:** Clause Classification
- **Note:** Returns the literal string `"not stated"` for absent fields rather than guessing.

#### 2. Clause Classification Agent
- **Role:** `Clause Classification Attorney`
- **Persona:** Judges a clause by its operative effect, not its heading — a clause titled "Miscellaneous" that caps damages is a Liability clause.
- **Input:** Clause text + heading + the allowed 20-category taxonomy.
- **Output:** `category`, `confidence`, `rationale`, `alternatives[]`, `key_terms[]`
- **Hands off to:** Playbook Validation, Risk Assessment
- **Guards:** An out-of-taxonomy category is rejected and replaced by the heuristic's. Confidence is clamped to 0–1. **When the model disagrees with the deterministic classifier and the heuristic is confident, confidence is damped to ≤0.62** — disagreement is real evidence of ambiguity, and the hallucination guardrail then surfaces it.

#### 3. Playbook Validation Agent
- **Role:** `Playbook Compliance Officer`
- **Persona:** Applies written rules literally and refuses to improvise.
- **Input:** Clause text + category + the playbook rules Qdrant retrieved.
- **Output:** `compliant`, `violations[{rule_id, detail, severity}]`, `matched_rule_ids[]`, `assessment`
- **Uses Qdrant:** ✅ Playbook RAG
- **Hands off to:** Risk Assessment
- **Guards:** Monetary and duration thresholds are evaluated **deterministically** — arithmetic is not delegated to a language model. Violations citing a rule id that does not exist are dropped. Deterministic findings win on conflict.

#### 4. Risk Assessment Agent
- **Role:** `Contract Risk Analyst`
- **Persona:** Names the mechanism of harm — not "this is risky" but "this permits termination on 5 days notice with no cure period, stranding in-flight work".
- **Input:** Clause + category + retrieved rules + similar historical clauses + the deterministic baseline.
- **Output:** `risk_score` 0–100, `risk_level`, `explanation`, `suggested_fix`, `financial_exposure`, `triggered_rule_ids[]`
- **Uses Qdrant:** ✅ Playbook rules + similar clauses
- **Hands off to:** Redline, Escalation
- **Scoring:** `0.6 × model + 0.4 × deterministic`. The baseline anchors the score to policy arithmetic; the model contributes reading comprehension. Pure-LLM scores drift badly between runs. **A fired playbook rule sets a floor at the High threshold** — policy is not negotiable by model opinion.

#### 5. Redline Agent
- **Role:** `Redline Drafting Attorney`
- **Persona:** Changes only what must change, because every extra edit is another thing the counterparty argues about.
- **Input:** Clause + risk explanation + target fix + approved precedent language.
- **Output:** `original`, `suggested`, `reason`, `change_summary`, `materiality`, `confidence`
- **Uses Qdrant:** ✅ Precedent Recall
- **Hands off to:** Organization Negotiator, Escalation
- **Guards:** `original` is always echoed from the true source, never the model's copy of it.

### Negotiation agents

#### 6. Organization Agent
- **Role:** `Organization Negotiator`
- **Persona:** In-house counsel for our side. Commercially pragmatic, not obstructive: concedes low-value points to win the ones that matter, never re-litigates a conceded point, and moves toward closure as rounds run down.
- **Output:** `message`, `stance` (counter/accept/reject/escalate), `proposed_language`, `concession`, `projected_risk_score`
- **Uses Qdrant:** ✅ Negotiation memory
- **Hands off to:** Counterparty Agent, Escalation, Audit

#### 7. Counterparty Agent
- **Role:** `Counterparty Negotiator`
- **Persona:** Outside counsel defending their standard terms — a realistic adversary, not a pushover and not a cartoon villain. Has genuine authority limits it will not cross without escalation, and concedes gradually when pressed with a credible rationale.
- **Output:** Same shape as the Organization Agent.
- **Uses Qdrant:** ✅ Negotiation memory
- **Hands off to:** Organization Agent, Escalation, Audit

The loop runs in
[`NegotiationOrchestrator`](../backend/app/agents/pipeline.py) for N rounds
(default 4). It ends `accepted` when **both** sides accept in the same round,
`rejected`/`escalated` on an explicit stance, or `escalated` on deadlock when the
rounds run out. Only our own side's proposed language is adopted as the working
draft — the counterparty's proposal is a position, not our draft.

### Governance agents

#### 8. Escalation Agent
- **Role:** `Escalation Triage Officer`
- **Persona:** Deliberately conservative — a false escalation costs a reviewer ten minutes, a missed one costs a lawsuit.
- **Output:** `should_escalate`, `priority`, `assigned_role`, `reason`, `recommended_action`, `sla_hours`
- **Hands off to:** Audit
- **Policy floor (overrides the model):** risk ≥ High threshold, risk level High/Critical, deadlock, an unresolved playbook breach, **or** low agent confidence *combined with* at least Medium risk. Low confidence alone does not escalate — a preamble is inherently hard to categorise, and escalating boilerplate trains reviewers to ignore the queue. An escalated item is never labelled "low" priority.

#### 9. Audit Agent
- **Role:** `Audit and Compliance Recorder`
- **Persona:** Writes neutral, factual entries a regulator could read years later. Never editorialises, never omits an unfavourable fact.
- **Output:** `summary`, `compliance_note`
- **Note:** Narration is opt-in per event (it costs an LLM call) and is used for decisions a human will actually read. The hash chain is independent of the narration.

### Supporting agents

#### 10. Negotiation Strategy Coach — *Feature 3*
- **Role:** `Negotiation Strategy Coach`
- **Output:** `acceptance_probability` 0–100, `recommended_move`, `leverage_assessment`, `risks_of_pushing`, `walk_away_signal`
- **Uses Qdrant:** ✅ Negotiation memory
- Gives **one** concrete next move, not a list of options.

#### 11. Executive AI Summary Agent — *Feature 5*
- **Role:** `Executive Briefing Analyst`
- **Persona:** A chief of staff briefing a CEO who has four minutes and no legal training.
- **Output:** headline, obligations, financial exposure, deadlines, renewal, top risks, recommended actions, overall recommendation.

---

## 3. Orchestration

### Production path — `run_clause_review_pipeline()`

Per clause, with typed hand-offs so downstream agents receive real structure:

```
Clause Classification ──► Playbook Validation ──► Risk Assessment ──► Redline ──► Escalation
        │                        ▲                      ▲                ▲
        │                        │                      │                │
    category            Qdrant: playbook       Qdrant: similar     Qdrant: precedents
                          rules for this          clauses in         approved for this
                            category            other contracts        category
```

Each step executes as a Lyzr `Task`. Redline is skipped for Low-risk clauses —
there is nothing to fix.

### Native path — `run_lyzr_linear_pipeline()`

The same four agents assembled into a genuine `LinearSyncPipeline` with
`input_tasks` wiring, so Lyzr's own chaining and task logging drive execution:

```python
classify  = classifier.build_task(default_input=clause_payload, name="1-classify")
validate  = validator.build_task(..., name="2-playbook", input_tasks=[classify])
assess    = assessor.build_task(...,  name="3-risk",     input_tasks=[classify, validate])
redline   = redliner.build_task(...,  name="4-redline",  input_tasks=[assess])

LinearSyncPipeline(tasks=[classify, validate, assess, redline], name="dharma-clause-review").run()
```

`Task` is text-in/text-out by design, so this route yields the framework's own
chaining rather than typed hand-offs — which is exactly what makes it worth
exposing. `POST /api/agents/pipeline/demo` runs it and returns every task with its
agent role, `input_tasks` and parsed output.

### Full journey

```
   Upload
     │
     ▼
  Extract text ──► GUARDRAIL: prompt injection + PII ──► (block or neutralise)
     │
     ▼
  Split into clauses ──► embed into Qdrant
     │
     ▼
  Contract Parsing Agent
     │
     ▼
  ┌── per clause ─────────────────────────────────────────┐
  │  Classification → Playbook → Risk → Redline → Escalate │
  └───────────────────────────────────────────────────────┘
     │
     ├──► GUARDRAIL: hallucination flag on each agent output
     ├──► GUARDRAIL: human-approval gate on each redline
     │
     ▼
  Contract risk rollup (category-weighted + severity concentration)
     │
     ▼
  Negotiation: Organization ⇄ Counterparty × N rounds
     │              (Strategy Coach after each of our turns)
     ▼
  Escalation Agent ──► human review queue ──► approve / edit / reject
     │                                              │
     │                                              ▼
     │                                   approved wording ──► Qdrant precedents
     ▼
  Audit Agent records every step, hash-chained
```

---

## 4. Failure behaviour

Every agent degrades rather than raising, because one bad LLM response must not
take down a pipeline mid-demo:

| Failure | Behaviour |
| --- | --- |
| Malformed JSON | One repair pass (the model is shown its own bad output), then the typed fallback. |
| Unparseable after repair | Deterministic heuristic result, tagged `method: "heuristic-fallback"`. |
| Network / API error | Same fallback; the error is recorded in call telemetry. |
| No API key | Demo mode: deterministic fixtures derived from the real clause text. Agents still run through genuine Lyzr `Task` objects — only the final network hop is replaced. |
| Out-of-range numbers | Clamped (`clamp()` in `base.py`). |
| Hallucinated rule ids | Dropped — a cited rule must exist. |
| Degraded path used | The hallucination guardrail flags `method: *fallback*` as a reliability signal. |

Demo mode exists because a demo that dies on a rate limit is a lost demo. It is
reported honestly in `/api/health` and in the app header — never disguised as
live inference.

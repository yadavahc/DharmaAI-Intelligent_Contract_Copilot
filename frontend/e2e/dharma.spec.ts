import { expect, test, type Page } from "@playwright/test";

/**
 * End-to-end journey: upload → classify → negotiate → escalate.
 *
 * Runs against the real stack (Next.js + FastAPI + the agent pipeline) with the
 * backend in demo mode, so the agents execute through genuine Lyzr `Task`
 * objects but the final LLM hop is deterministic. That makes the test a real
 * integration test rather than a mock, while staying fast and unflaky.
 *
 * Prerequisites (see README):
 *   backend:  DHARMA_DEMO_MODE=true uvicorn app.main:app --port 8000
 *   frontend: npm run build && npm run start
 */

const API = process.env.E2E_API_URL || "http://localhost:8000";

const REVIEWER = {
  email: process.env.DEMO_REVIEWER_EMAIL || "reviewer@dharma.ai",
  password: process.env.DEMO_REVIEWER_PASSWORD || "reviewer123",
};

const BUSINESS_USER = {
  email: process.env.DEMO_USER_EMAIL || "user@dharma.ai",
  password: process.env.DEMO_USER_PASSWORD || "user123",
};

async function signIn(page: Page, who: { email: string; password: string }) {
  await page.goto("/signin");
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 45_000 });
}

test.beforeAll(async ({ request }) => {
  // Fail loudly and usefully if the backend is not up, rather than letting every
  // assertion time out with an opaque error.
  let health;
  try {
    health = await request.get(`${API}/api/health`, { timeout: 10_000 });
  } catch (error) {
    throw new Error(
      `Dharma AI backend is not reachable at ${API}. Start it with:\n` +
        `  cd backend && DHARMA_DEMO_MODE=true uvicorn app.main:app --port 8000\n` +
        `Original error: ${String(error)}`,
    );
  }
  expect(health.ok(), `Backend health check failed (${health.status()})`).toBeTruthy();

  const body = await health.json();
  // Reset to a known-empty state so counts and the queue are deterministic.
  const reset = await request.post(
    `${API}/api/demo/reset?include_vectors=true&load_sample=false`,
    { timeout: 60_000 },
  );
  expect(reset.ok(), "Demo reset failed").toBeTruthy();

  console.log(
    `[e2e] backend ready — lyzr=${body.lyzr?.lyzr_runtime} ` +
      `genuine=${body.lyzr?.is_genuine_sdk} demo_mode=${body.demo_mode} ` +
      `db=${body.database?.backend} vectors=${body.vector_store?.backend}`,
  );
});

test.describe("Dharma AI end-to-end journey", () => {
  test("upload → classify → negotiate → escalate → approve", async ({ page }) => {
    // ─────────────────────────────────────────────────────────────────────
    test.step("sign in as a Reviewer", async () => {});
    await signIn(page, REVIEWER);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

    // ── 1. UPLOAD ────────────────────────────────────────────────────────
    let contractId = "";

    await test.step("upload a contract", async () => {
      await page.goto("/upload");
      await expect(page.getByRole("heading", { name: /upload a contract/i })).toBeVisible();

      // The bundled sample is a 17-clause MSA written to trip many rules.
      await page.getByRole("button", { name: /use the sample contract/i }).click();

      await page.waitForURL(/\/contracts\/[0-9a-f-]{36}/, { timeout: 60_000 });
      contractId = page.url().split("/contracts/")[1];
      expect(contractId).toMatch(/^[0-9a-f-]{36}$/);
    });

    // ── 2. CLASSIFY (the agent review pipeline) ──────────────────────────
    await test.step("run the agent review and see clauses classified", async () => {
      await expect(page.getByTestId("run-review")).toBeVisible({ timeout: 30_000 });
      await page.getByTestId("run-review").click();

      // The review streams over SSE; wait for the contract-level score to land.
      await expect(page.getByText(/contract risk/i).first()).toBeVisible({
        timeout: 120_000,
      });

      const clauseRows = page.getByTestId("clause-row");
      await expect(clauseRows.first()).toBeVisible({ timeout: 60_000 });
      const clauseCount = await clauseRows.count();
      expect(clauseCount).toBeGreaterThanOrEqual(10);

      // Classification produced real categories, not placeholders.
      await expect(page.getByText("Liability", { exact: true }).first()).toBeVisible();

      // At least one clause reached High or Critical on this deliberately bad MSA.
      await expect(
        page.locator('[data-testid="clause-row"]').filter({ hasText: /Critical|High/ }).first(),
      ).toBeVisible();
    });

    // ── 3. NEGOTIATE (the two-agent theater) ─────────────────────────────
    let clauseId = "";

    await test.step("negotiate the highest-risk clause", async () => {
      // Pick the worst clause via the API so the test does not depend on
      // whatever order the UI happens to render.
      const response = await page.request.get(`${API}/api/contracts/${contractId}`);
      expect(response.ok()).toBeTruthy();
      const contract = await response.json();

      const worst = [...contract.clauses].sort(
        (a: { risk_score: number }, b: { risk_score: number }) => b.risk_score - a.risk_score,
      )[0];
      clauseId = worst.id;
      expect(worst.risk_score).toBeGreaterThan(0);

      await page.goto(`/negotiations/${clauseId}`);
      await expect(page.getByText(/live agent theater/i)).toBeVisible();

      await page.getByTestId("start-negotiation").click();

      // Both agents must actually speak.
      const turns = page.getByTestId("negotiation-turn");
      await expect(turns.first()).toBeVisible({ timeout: 90_000 });
      await expect
        .poll(async () => turns.count(), { timeout: 120_000, intervals: [1000] })
        .toBeGreaterThanOrEqual(4);

      await expect(page.getByText("Organization Agent").first()).toBeVisible();
      await expect(page.getByText("Counterparty Agent").first()).toBeVisible();

      // Feature 3: the Strategy Coach produced an acceptance probability.
      await expect(page.getByTestId("strategy-coach")).toContainText(
        /acceptance probability/i,
      );

      // The negotiation reached a terminal outcome.
      await expect(page.getByTestId("negotiation-outcome")).toBeVisible({
        timeout: 120_000,
      });
    });

    // ── 4. ESCALATE (human review queue) ─────────────────────────────────
    await test.step("escalated clauses reach the human review queue", async () => {
      await page.goto("/review");
      await expect(page.getByRole("heading", { name: /review queue/i })).toBeVisible();

      const tasks = page.getByTestId("review-task");
      await expect(tasks.first()).toBeVisible({ timeout: 30_000 });
      expect(await tasks.count()).toBeGreaterThan(0);

      // The Escalation Agent recorded why a human is needed.
      await expect(tasks.first()).toContainText(/priority/i);
    });

    // ── 5. APPROVAL GATE ─────────────────────────────────────────────────
    await test.step("a Reviewer can pass the approval gate", async () => {
      const firstTask = page.getByTestId("review-task").first();
      await firstTask.click();

      const approve = page.getByTestId("approve-redline").first();
      await expect(approve).toBeVisible({ timeout: 20_000 });
      await expect(approve).toBeEnabled();
      await approve.click();

      // A toast confirms the gate transition.
      await expect(page.getByText(/redline approved|approval gate/i).first()).toBeVisible({
        timeout: 30_000,
      });
    });

    // ── 6. AUDIT (immutability) ──────────────────────────────────────────
    await test.step("the audit chain records everything and verifies", async () => {
      await page.goto("/audit");
      await expect(page.getByRole("heading", { name: /audit log/i })).toBeVisible();

      const rows = page.getByTestId("audit-row");
      await expect(rows.first()).toBeVisible({ timeout: 30_000 });
      expect(await rows.count()).toBeGreaterThan(3);

      await page.getByTestId("verify-chain").click();
      const verification = page.getByTestId("chain-verification");
      await expect(verification).toBeVisible({ timeout: 30_000 });
      await expect(verification).toContainText(/chain intact/i);
    });
  });

  test("guardrails fire on live input", async ({ page }) => {
    await signIn(page, REVIEWER);
    await page.goto("/guardrails");

    await test.step("prompt injection is detected and neutralised", async () => {
      await page.getByTestId("guardrail-tab-prompt_injection").click();
      await page.getByTestId("run-guardrail").click();

      const verdict = page.getByTestId("guardrail-prompt_injection");
      await expect(verdict).toBeVisible({ timeout: 30_000 });
      await expect(verdict).toContainText(/critical/i);
      await expect(verdict).toContainText(/instruction_override|risk_manipulation/);
    });

    await test.step("PII is detected and redacted", async () => {
      await page.getByTestId("guardrail-tab-pii_detection").click();
      await page.getByTestId("run-guardrail").click();

      const verdict = page.getByTestId("guardrail-pii_detection");
      await expect(verdict).toBeVisible({ timeout: 30_000 });
      await expect(verdict).toContainText(/us_ssn|credit_card/);
      // The report must never echo the raw value.
      await expect(verdict).not.toContainText("123-45-6789");
    });

    await test.step("hallucinated claims are flagged", async () => {
      await page.getByTestId("guardrail-tab-hallucination_flag").click();
      await page.getByTestId("run-guardrail").click();

      const verdict = page.getByTestId("guardrail-hallucination_flag");
      await expect(verdict).toBeVisible({ timeout: 30_000 });
      await expect(verdict).toContainText(/unsupported_quotation|very_low_confidence/);
    });

    await test.step("the approval gate refuses an unauthorised role", async () => {
      await page.getByTestId("guardrail-tab-approval_gate").click();
      // Default acting role is Business User, which is not authorised.
      await page.getByTestId("run-guardrail").click();

      const result = page.getByTestId("gate-attempt-result");
      await expect(result).toBeVisible({ timeout: 30_000 });
      await expect(result).toContainText(/refused/i);
      await expect(result).toContainText(/may not approve/i);
    });
  });

  test("a Business User cannot approve redlines", async ({ page }) => {
    await signIn(page, BUSINESS_USER);
    await page.goto("/review");

    // The role restriction is stated, and the action is disabled.
    await expect(page.getByText(/read-only for your role/i)).toBeVisible();

    const tasks = page.getByTestId("review-task");
    if ((await tasks.count()) > 0) {
      await tasks.first().click();
      await expect(page.getByTestId("approve-redline").first()).toBeDisabled();
    }

    // Playbook management is admin-only.
    await page.goto("/playbook");
    await expect(page.getByText(/admin access required/i)).toBeVisible();
  });
});

import { expect, test, type Page } from "@playwright/test";

// Smoke tests. They need the API running at :8001 with seeded users and indexed demo docs.

async function signInAs(page: Page, email: string) {
  await page.addInitScript((e) => localStorage.setItem("copilot.user", e), email);
}

test("overview shows key numbers and hands a question to the copilot", async ({ page }) => {
  await signInAs(page, "agent@tasklane.example");
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Good");
  await expect(page.getByText("Documents indexed")).toBeVisible();
  await expect(page.getByText("Retrieval quality by mode")).toBeVisible();

  await page.getByLabel("Ask the copilot").fill("What does error SSO-401 mean?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page).toHaveURL(/\/copilot$/);
  await expect(page.getByTestId("assistant-answer")).toBeVisible({ timeout: 60_000 });
});

test("sources page lists ready documents", async ({ page }) => {
  await signInAs(page, "agent@tasklane.example");
  await page.goto("/sources");
  const rows = page.getByTestId("source-row");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(0);
  await expect(page.getByTestId("sources-table").getByText("ready").first()).toBeVisible();

  // The chunk viewer opens for a document.
  await rows.first().getByRole("button", { name: "Chunks" }).click();
  await expect(page.getByTestId("chunk").first()).toBeVisible();
});

test("copilot answers an example question with citation chips and a trace", async ({ page }) => {
  await signInAs(page, "agent@tasklane.example");
  await page.goto("/copilot");
  await page.getByTestId("customer-picker").selectOption({ label: "Brightpath Logistics (CUST-1001)" });
  await expect(page.getByTestId("customer-card")).toContainText("suspended");

  await page.getByRole("button", { name: "Why can't the team create tasks or upload files?" }).click();
  await expect(page.getByTestId("copilot-loading")).toBeVisible();

  const answer = page.getByTestId("assistant-answer");
  await expect(answer).toBeVisible({ timeout: 60_000 });
  const chip = answer.getByTestId("citation-chip").first();
  await expect(chip).toBeVisible();
  await chip.click();
  await expect(answer.getByTestId("citation-card").first()).toBeVisible();

  await answer.getByRole("button", { name: "View retrieval trace" }).click();
  await expect(page.getByTestId("trace-table")).toBeVisible();
  await expect(page.getByTestId("trace-table").getByText("selected").first()).toBeVisible();
});

test("off-topic question shows the abstention banner", async ({ page }) => {
  await signInAs(page, "agent@tasklane.example");
  await page.goto("/copilot");
  await page.getByTestId("question-input").fill("What is the capital of France?");
  await page.getByTestId("question-input").press("Enter");
  await expect(page.getByTestId("abstained-banner")).toBeVisible({ timeout: 60_000 });
});

// Offline mode never proposes actions, so serve one pending action from a mocked endpoint.
const pendingAction = {
  id: "11111111-1111-1111-1111-111111111111",
  action_type: "add_ticket_tag",
  status: "pending",
  customer: "Brightpath Logistics",
  ticket: "TCK-2001",
  ticket_subject: "Cannot create tasks",
  value: "billing-suspension",
  final_value: null,
  reason: "Workspace is suspended for non-payment.",
  proposed_by: "22222222-2222-2222-2222-222222222222",
  decided_by: null,
  decided_at: null,
  decision_note: null,
  result: null,
  error: null,
  message_id: null,
  created_at: "2026-11-04T12:00:00Z",
};

test("viewer cannot see approve buttons; agent can", async ({ page }) => {
  await page.route("**/api/actions*", (route) =>
    route.fulfill({ json: [pendingAction] }),
  );

  await signInAs(page, "viewer@tasklane.example");
  await page.goto("/actions");
  const row = page.getByTestId("action-row");
  await expect(row).toBeVisible();
  await expect(page.getByTestId("decision-not-allowed")).toBeVisible();
  await expect(row.getByRole("button", { name: /Approve/ })).toHaveCount(0);

  // Switch to the agent via the user menu in the sidebar: the buttons appear.
  await page.getByTestId("user-switcher").click();
  await page.getByRole("menuitemradio", { name: /Sam Agent/ }).click();
  await expect(page.getByTestId("action-row").getByRole("button", { name: "Approve" })).toBeVisible();
  await expect(page.getByTestId("action-row").getByRole("button", { name: "Reject" })).toBeVisible();
});

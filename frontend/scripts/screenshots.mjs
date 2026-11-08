// README screenshots from the running stack: `npm run screenshots` (needs the demo seeded and
// indexed; the copilot shots need an LLM). Reset first for a clean state:
//   docker compose exec api python -m scripts.reset_demo --yes
// Writes docs/screenshots/*.png. BASE_URL defaults to http://localhost:3002.
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3002";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots");
const ANSWER_TIMEOUT = 180_000;
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  baseURL: BASE_URL,
  viewport: { width: 1440, height: 900 },
  colorScheme: "light",
});
await context.addInitScript(() => {
  localStorage.setItem("copilot.user", "agent@tasklane.example");
  localStorage.setItem("theme", "light");
});
const page = await context.newPage();
const shot = async (name, options = {}) => {
  await page.waitForTimeout(600); // let entrance animations settle
  await page.screenshot({ path: join(OUT, `${name}.png`), ...options });
  console.log(`saved ${name}.png`);
};

// Copilot: a cited answer from docs + the CRM tool, then a proposed ticket note.
await page.goto("/copilot");
await page.getByTestId("customer-picker").selectOption({ label: "Brightpath Logistics (CUST-1001)" });
const ask = async (question, count) => {
  await page.getByTestId("question-input").fill(question);
  await page.getByTestId("question-input").press("Enter");
  await page.getByTestId("assistant-answer").nth(count - 1).waitFor({ timeout: ANSWER_TIMEOUT });
};
await ask("Why can't the team create tasks or upload files?", 1);
await shot("copilot-answer");
await ask("Add an internal note to their open ticket summarizing why they're blocked.", 2);
await page.getByTestId("assistant-answer").nth(1).scrollIntoViewIfNeeded();
await shot("copilot-proposal");

// Approvals: the proposal waits for a human.
await page.goto("/actions");
await page.getByTestId("action-row").first().waitFor();
await shot("approvals");

// Search lab: the same query through all four retrieval modes.
await page.goto("/search");
await page.getByTestId("search-query").fill("SSO-409");
await page.getByText("Compare all four modes").click();
await page.getByTestId("results-hybrid_rerank").waitFor({ timeout: 60_000 });
await shot("search-lab");

// Overview and the evaluation report.
await page.goto("/");
await page.getByText("Retrieval quality by mode").waitFor();
// Recharts draws the bar value labels only once the bars finish animating.
await page.locator(".recharts-label-list").first().waitFor();
await shot("overview");
await page.goto("/evals");
await page.getByTestId("eval-report").waitFor();
await page.locator(".recharts-label-list").first().waitFor();
await shot("evaluations");

await browser.close();

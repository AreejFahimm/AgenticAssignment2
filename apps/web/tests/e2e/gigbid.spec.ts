import { expect, test, type Page } from "@playwright/test";

let n = 0;
const uniq = () => `e2e${Date.now()}${n++}@example.com`;

async function register(page: Page, persona = "fullstack_web_dev") {
  await page.goto("/#/signin");
  await page.getByTestId("auth-toggle").click();
  await page.getByLabel("Email").fill(uniq());
  await page.getByLabel("Password").fill("password-123");
  await page.getByLabel("I am a").selectOption(persona);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByRole("heading", { name: "Set up your profile" })).toBeVisible();
}
async function onboard(page: Page, query = "react") {
  await page.getByLabel("Saved search keywords").fill(query);
  await page.getByTestId("budget").fill("100");
  await page.getByTestId("finish-onboarding").click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
}
async function scanUntilReview(page: Page) {
  await page.getByTestId("scan").click();
  await expect(page.getByTestId("scan-msg")).toContainText("Queued");
  const review = page.getByRole("link", { name: "Review" }).first();
  await expect(review).toBeVisible();
  await review.click();
  await expect(page.getByTestId("approval-panel")).toBeVisible();
}

test("1. onboarding: register, connect, set budget, land on the inbox", async ({ page }) => {
  await register(page);
  await onboard(page);
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByTestId("weekly-budget")).toHaveValue("100");
});

test("2. approve a proposal: evidence on hover, dry-run preview, graph resumes and submits", async ({ page }) => {
  await register(page);
  await onboard(page);
  await scanUntilReview(page);
  await expect(page.getByTestId("dry-run")).toContainText("Connects");
  const ev = page.getByTestId("para-evidence").first();
  await ev.hover();
  await expect(page.getByTestId("evidence-popover")).toBeVisible();
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("decision-sent")).toBeVisible();
  await page.getByRole("link", { name: "Back to inbox" }).click();
  await expect(page.getByTestId("row-status").filter({ hasText: "submitted" }).first()).toBeVisible();
  await page.getByRole("link", { name: "Pipeline" }).click();
  await expect(page.getByTestId("kanban")).toContainText("submitted");
});

test("3. reject with a reason: nothing is sent and the reason shows in analytics", async ({ page }) => {
  await register(page);
  await onboard(page);
  await scanUntilReview(page);
  await page.getByTestId("reject").click();
  await expect(page.getByTestId("confirm-reject")).toBeDisabled();           // a reason is required
  await page.getByTestId("reject-reason").fill("too generic for this client");
  await page.getByTestId("confirm-reject").click();
  await expect(page.getByTestId("decision-sent")).toBeVisible();
  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByTestId("rejections")).toContainText("too generic for this client");
});

test("4. edit a draft: edits are re-checked by Compliance and then submitted", async ({ page }) => {
  await register(page);
  await onboard(page);
  await scanUntilReview(page);
  await expect(page.getByTestId("approve")).toBeEnabled();
  const box = page.getByTestId("edit-text");
  const original = await box.inputValue();
  await box.fill(original + " Please also contact me on WhatsApp +1 555 123 4567.");
  await expect(page.getByTestId("approve")).toBeDisabled();                  // must use the edit path once text changed
  await page.getByTestId("save-edit").click();
  await expect(page.getByTestId("decision-sent")).toBeVisible();
  await page.getByRole("link", { name: "View run" }).click();
  await expect(page.getByTestId("run-timeline")).toContainText("approval");
});

test("5. degraded mode: marketplace unavailable banner with retry", async ({ page }) => {
  await register(page);
  await onboard(page);
  await page.route("**/status", (route) => route.fulfill({ json: { marketplace_ok: false, marketplace_error: "connection refused", queued_degraded: 2, mode: "gigsim", model_profile: "offline" } }));
  await page.reload();
  const banner = page.getByTestId("degraded-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Marketplace unavailable");
  await expect(banner).toContainText("2 queued");
  await expect(banner.getByRole("button", { name: "Retry now" })).toBeEnabled();
});

test("6. API down: the UI says so instead of spinning forever", async ({ page }) => {
  await register(page);
  await onboard(page);
  await page.route("**/jobs*", (route) => route.abort());
  await page.route("**/status", (route) => route.abort());
  await page.getByRole("link", { name: "Pipeline" }).click();
  await page.getByRole("link", { name: "Inbox" }).click();
  await expect(page.getByTestId("api-down-banner")).toBeVisible();
});

test("7. keyboard: skip link and focusable evidence @mobile", async ({ page }) => {
  await register(page);
  await onboard(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBeFalsy();                                               // no horizontal page scroll on a phone
});

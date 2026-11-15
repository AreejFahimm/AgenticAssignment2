// Records a screen video of one job from inbox to approved proposal to client reply (portfolio deliverable).
//   cd apps/web && npx playwright test demo.spec.ts --project=demo     -> test-results/**/video.webm  (convert to GIF/MP4 with ffmpeg)
import { expect, test } from "@playwright/test";

test.use({ video: { mode: "on", size: { width: 1280, height: 720 } }, viewport: { width: 1280, height: 720 } });

test("demo: inbox -> approved proposal -> client reply", async ({ page }) => {
  const email = `demo${Date.now()}@example.com`;
  await page.goto("/#/signin");
  await page.getByTestId("auth-toggle").click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password-123");
  await page.getByLabel("I am a").selectOption("fullstack_web_dev");
  await page.getByTestId("auth-submit").click();
  await page.getByLabel("Saved search keywords").fill("react");
  await page.getByTestId("finish-onboarding").click();
  await page.getByTestId("scan").click();
  const review = page.getByRole("link", { name: "Review" }).first();
  await expect(review).toBeVisible();
  await page.waitForTimeout(1500);
  await review.click();
  await page.getByTestId("para-evidence").first().hover();           // evidence on hover
  await page.waitForTimeout(1500);
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("decision-sent")).toBeVisible();
  await page.getByRole("link", { name: "Pipeline" }).click();
  await page.waitForTimeout(1500);
  await page.getByRole("link", { name: "Messages" }).click();
  const draft = page.getByTestId("draft-reply").first();
  if (await draft.isVisible({ timeout: 20_000 }).catch(() => false)) {
    await draft.click();
    await expect(page.getByTestId("reply-approval")).toBeVisible();
    await page.waitForTimeout(1500);
    await page.getByTestId("send-reply").click();
  }
  await page.waitForTimeout(1500);
});

import { chromium } from "@playwright/test";
import { pathToFileURL } from "node:url";
const [,, src, out] = process.argv;
const b = await chromium.launch(); const p = await b.newPage();
await p.goto(pathToFileURL(src).href);
await p.pdf({ path: out, format: "A4", margin: { top: "14mm", bottom: "14mm", left: "13mm", right: "13mm" }, printBackground: true });
await b.close();

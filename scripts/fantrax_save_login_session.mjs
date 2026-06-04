#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import readline from "node:readline/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, "..");
const bundledNodeModules = "/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const requireFromBundle = createRequire(path.join(bundledNodeModules, "package.json"));
const { chromium } = requireFromBundle("playwright");

const leagueId = process.env.FANTRAX_LEAGUE_ID || "qqll39pvmj90wrl1";
const profileDir = process.env.FANTRAX_BROWSER_PROFILE_DIR || path.join(projectRoot, ".fantrax-browser-profile");
const cookiePath = process.env.FANTRAX_AUTH_COOKIE_FILE || path.join(projectRoot, "outputs", "fantrax_export", "fantrax_auth_cookie_latest.txt");
const fantraxUrl = `https://www.fantrax.com/fantasy/league/${leagueId}/home`;
const executablePath = process.env.FANTRAX_BROWSER_EXECUTABLE_PATH || "";

async function writeCookieHeader(context) {
  const cookies = await context.cookies("https://www.fantrax.com");
  const header = cookies
    .filter((cookie) => cookie.name && cookie.value)
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");
  if (!header) {
    throw new Error("No fantrax.com cookies were found. Make sure you are logged in before pressing Enter.");
  }
  await fs.mkdir(path.dirname(cookiePath), { recursive: true });
  await fs.writeFile(cookiePath, `${header}\n`, { mode: 0o600 });
  return { cookieCount: cookies.length, cookiePath };
}

const context = await chromium.launchPersistentContext(profileDir, {
  headless: false,
  viewport: { width: 1440, height: 960 },
  ...(executablePath ? { executablePath } : {}),
});

try {
  const page = context.pages()[0] || await context.newPage();
  await page.goto(fantraxUrl, { waitUntil: "domcontentloaded" });

  console.log("Fantrax login setup");
  console.log(`Browser profile: ${profileDir}`);
  console.log("Log in to Fantrax in the opened browser window.");
  console.log("When the league page is visible, return here and press Enter.");

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  await rl.question("");
  rl.close();

  const result = await writeCookieHeader(context);
  console.log(`Saved ${result.cookieCount} Fantrax cookies to ${result.cookiePath}`);
} finally {
  await context.close();
}

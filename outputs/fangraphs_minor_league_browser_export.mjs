#!/usr/bin/env node
import { access, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const defaultOutDir = path.join(projectRoot, "outputs", "minor_league_hitter_stars", "fangraphs_exports");
const reports = [
  ["standard", 0],
  ["advanced", 1],
  ["batted", 2],
];
const defaultLeagues = [2, 4, 5, 6, 7, 11, 14, 13, 8, 9, 10, 16, 17, 30];
const defaultYears = [2025];

function parseArgs(argv) {
  const args = {
    years: defaultYears,
    outDir: defaultOutDir,
    leagues: defaultLeagues,
    headful: false,
    pageItems: 1000,
    minDelayMs: 60000,
    maxDelayMs: 90000,
    skipExisting: true,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--year") args.years = [Number(argv[++i])];
    else if (arg === "--years") args.years = argv[++i].split(",").filter(Boolean).map(Number);
    else if (arg === "--out-dir") args.outDir = path.resolve(argv[++i]);
    else if (arg === "--leagues") args.leagues = argv[++i].split(",").filter(Boolean).map(Number);
    else if (arg === "--headful") args.headful = true;
    else if (arg === "--page-items") args.pageItems = Number(argv[++i]);
    else if (arg === "--min-delay-sec") args.minDelayMs = Number(argv[++i]) * 1000;
    else if (arg === "--max-delay-sec") args.maxDelayMs = Number(argv[++i]) * 1000;
    else if (arg === "--delay-ms") {
      const delayMs = Number(argv[++i]);
      args.minDelayMs = delayMs;
      args.maxDelayMs = delayMs;
    }
    else if (arg === "--overwrite") args.skipExisting = false;
    else if (arg === "-h" || arg === "--help") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function printHelp() {
  console.log(`Usage: fangraphs_minor_league_browser_export.mjs [options]

Options:
  --year YEAR          Season to export. Default: 2025
  --years YEARS        Comma-separated seasons to export, e.g. 2025,2026
  --leagues IDS        Comma-separated FanGraphs league ids. Default: affiliated minor leagues
  --out-dir PATH       Folder for CSV exports. Default: outputs/minor_league_hitter_stars/fangraphs_exports
  --headful            Show the browser while exporting
  --page-items N       Leaderboard page size. Default: 1000
  --min-delay-sec N    Minimum random delay between FanGraphs page loads. Default: 60
  --max-delay-sec N    Maximum random delay between FanGraphs page loads. Default: 90
  --delay-ms N         Fixed delay between FanGraphs page loads, mainly for tests
  --overwrite          Re-export files that already exist
`);
}

async function exists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function randomDelayMs(minDelayMs, maxDelayMs) {
  if (!minDelayMs && !maxDelayMs) return 0;
  if (maxDelayMs < minDelayMs) {
    throw new Error("--max-delay-sec must be greater than or equal to --min-delay-sec");
  }
  return Math.floor(minDelayMs + Math.random() * (maxDelayMs - minDelayMs + 1));
}

function formatDuration(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

function leaderboardUrl({ year, leagueId, reportType, pageItems }) {
  const params = new URLSearchParams({
    pos: "all",
    lg: String(leagueId),
    stats: "bat",
    qual: "0",
    type: String(reportType),
    team: "",
    season: String(year),
    seasonEnd: String(year),
    org: "",
    ind: "0",
    splitTeam: "true",
    players: "",
    sort: "23,1",
    page: "1",
    pageitems: String(pageItems),
  });
  return `https://www.fangraphs.com/leaders/minor-league?${params.toString()}`;
}

async function waitForExportCsv(page, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const href = await page.evaluate(() => {
      const link = [...document.querySelectorAll("a")].find((anchor) =>
        (anchor.textContent || "").trim().includes("Export Data")
      );
      return link ? link.href : null;
    });
    if (href?.startsWith("data:application/csv")) {
      const encoded = href.slice(href.indexOf(",") + 1);
      return decodeURIComponent(encoded);
    }
    await page.waitForTimeout(750);
  }
  throw new Error("Timed out waiting for Export Data CSV link");
}

async function exportReport(page, args, year, leagueId, reportName, reportType) {
  const yearOutDir = path.join(args.outDir, String(year));
  await mkdir(yearOutDir, { recursive: true });
  const outPath = path.join(yearOutDir, `${leagueId}_${reportName}.csv`);
  if (args.skipExisting && await exists(outPath)) {
    console.log(`Skip existing ${outPath}`);
    return false;
  }

  const url = leaderboardUrl({ year, leagueId, reportType, pageItems: args.pageItems });
  console.log(`Fetch ${year} league ${leagueId} ${reportName}`);
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  const csv = await waitForExportCsv(page);
  await writeFile(outPath, csv, "utf8");
  const rows = csv.split(/\r?\n/).filter(Boolean).length - 1;
  console.log(`Wrote ${outPath} (${rows} rows)`);
  return true;
}

async function politeDelay(args) {
  const delayMs = randomDelayMs(args.minDelayMs, args.maxDelayMs);
  if (delayMs <= 0) return;
  console.log(`Waiting ${formatDuration(delayMs)} before next FanGraphs request`);
  await new Promise((resolve) => setTimeout(resolve, delayMs));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  await mkdir(args.outDir, { recursive: true });
  const browser = await chromium.launch({ headless: !args.headful });
  const context = await browser.newContext({
    acceptDownloads: true,
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
  });
  const page = await context.newPage();
  try {
    let madeRequest = false;
    for (const year of args.years) {
      for (const leagueId of args.leagues) {
        for (const [reportName, reportType] of reports) {
          if (madeRequest) await politeDelay(args);
          madeRequest = await exportReport(page, args, year, leagueId, reportName, reportType) || madeRequest;
        }
      }
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});

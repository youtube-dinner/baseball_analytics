import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const dataPath = new URL("./analytics_workbook_data.json", import.meta.url);
const data = JSON.parse(await fs.readFile(dataPath, "utf8"));
const projectRoot = new URL("../../", import.meta.url);
const outputDir = new URL("outputs/", projectRoot);
const outputPath = new URL("Fantasy_Baseball_Analytics_Formatted.xlsx", outputDir);

const workbook = Workbook.create();
const defaultSheet = workbook.worksheets.add("Notes");
defaultSheet.showGridLines = false;

defaultSheet.getRange("A1:D1").values = [["Fantasy Baseball Analytics", "", "", ""]];
defaultSheet.mergeCells("A1:D1");
defaultSheet.getRange("A1:D1").format = {
  fill: { color: "#0F766E" },
  font: { color: "#FFFFFF", bold: true, size: 16 },
};
defaultSheet.getRange("A3:B8").values = [
  ["pitching_score", "Overall Stuff+Command style z-score. Higher is better."],
  ["command_score", "Control/contact-quality component: rewards fewer walks and fewer meatballs. Higher is better."],
  ["whiff_percent", "Raw Baseball Savant whiff percentage. Higher is better."],
  ["FPts / FP/G", "Calculated locally from MLB stats and your Fantrax scoring rules."],
  ["7/14/30d", "Actual date-window Statcast/MLB performance, with sample gates for score columns."],
  ["Color scale", "Red = lower, yellow = middle, green = higher."],
];
defaultSheet.getRange("A3:B7").format.borders = { preset: "all", style: "thin", color: "#D9E2E1" };
defaultSheet.getRange("A3:B8").format.borders = { preset: "all", style: "thin", color: "#D9E2E1" };
defaultSheet.getRange("A3:A8").format = { fill: { color: "#E0F2F1" }, font: { bold: true } };
defaultSheet.getRange("A:B").format.columnWidthPx = 240;

function columnLetter(index) {
  let n = index + 1;
  let s = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function coerceRows(rows) {
  const headers = rows[0];
  return rows.map((row, r) => row.map((value, c) => {
    if (r === 0) return value;
    const header = headers[c] || "";
    if (value === "") return "";
    if (/score|percent|FPts|FP\/G|p_game|IP_per_Game|p_era|whiff|bb_|meatball|ERA|Fantasy Points|Average Fantasy/.test(header)) {
      const num = Number(value);
      return Number.isFinite(num) ? num : value;
    }
    return value;
  }));
}

function formatSheet(sheet, rows) {
  sheet.showGridLines = false;
  const matrix = coerceRows(rows);
  const rowCount = matrix.length;
  const colCount = matrix[0].length;
  const used = sheet.getRangeByIndexes(0, 0, rowCount, colCount);
  used.values = matrix;

  const header = sheet.getRangeByIndexes(0, 0, 1, colCount);
  header.format = {
    fill: { color: "#134E4A" },
    font: { color: "#FFFFFF", bold: true },
    wrapText: true,
  };
  used.format.borders = {
    insideHorizontal: { style: "thin", color: "#E5E7EB" },
    insideVertical: { style: "thin", color: "#F3F4F6" },
  };
  sheet.freezePanes.freezeRows(1);

  const tableRange = `A1:${columnLetter(colCount - 1)}${rowCount}`;
  const tableName = sheet.name.replace(/[^A-Za-z0-9]/g, "") + "Table";
  const table = sheet.tables.add(tableRange, true, tableName);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;

  const headers = matrix[0];
  const colorMetricNames = [
    "pitching_score",
    "command_score",
    "whiff_percent",
    "hitter_score",
    "batters_eye_score",
    "barrel_batted_rate",
  ];
  for (const [idx, name] of headers.entries()) {
    if (!colorMetricNames.some((metric) => name === metric || name.startsWith(`${metric}_`))) continue;
    if (rowCount < 2) continue;
    const range = sheet.getRangeByIndexes(1, idx, rowCount - 1, 1);
    range.conditionalFormats.add("colorScale", {
      criteria: [
        { type: "lowestValue", color: "#FCA5A5" },
        { type: "percentile", value: 50, color: "#FEF3C7" },
        { type: "highestValue", color: "#86EFAC" },
      ],
    });
    range.format.numberFormat = [["0.00"]];
  }

  for (const name of ["FPts", "FP/G", "Fantasy Points", "Average Fantasy Points per Game", "p_era", "IP_per_Game"]) {
    const idx = headers.indexOf(name);
    if (idx !== -1 && rowCount > 1) {
      sheet.getRangeByIndexes(1, idx, rowCount - 1, 1).format.numberFormat = [["0.00"]];
    }
  }

  headers.forEach((headerName, idx) => {
    const width = Math.min(220, Math.max(76, String(headerName).length * 9 + 24));
    sheet.getRangeByIndexes(0, idx, rowCount, 1).format.columnWidthPx = width;
  });
  const playerIdx = headers.indexOf("Player");
  if (playerIdx !== -1) sheet.getRangeByIndexes(0, playerIdx, rowCount, 1).format.columnWidthPx = 180;
  const oppIdx = headers.indexOf("Opponent");
  if (oppIdx !== -1) sheet.getRangeByIndexes(0, oppIdx, rowCount, 1).format.columnWidthPx = 170;
  const teamIdx = headers.indexOf("Team");
  if (teamIdx !== -1) sheet.getRangeByIndexes(0, teamIdx, rowCount, 1).format.columnWidthPx = 170;
}

for (const [sheetName, rows] of Object.entries(data)) {
  const sheet = workbook.worksheets.add(sheetName);
  formatSheet(sheet, rows);
}

console.log("built sheets");
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
});
console.log(errors.ndjson);

console.log("rendering preview");
const preview = await workbook.render({ sheetName: "Streaming Pitchers", range: "A1:T12", scale: 1.5, format: "png" });
await fs.writeFile(new URL("Fantasy_Baseball_Analytics_Formatted_preview.png", outputDir), new Uint8Array(await preview.arrayBuffer()));

console.log("exporting");
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(fileURLToPath(outputPath));

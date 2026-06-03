#!/usr/bin/env python3
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "outputs" / "fantasy_baseball_analytics"
OUT = ROOT / "outputs" / "Fantasy_Baseball_Analytics_Sortable.html"

SHEETS = [
    ("Streaming Pitchers", "streaming_pitcher_analytics.csv"),
    ("Free Agent Pitchers", "free_agent_pitchers.csv"),
    ("Free Agent Hitters", "free_agent_hitters.csv"),
    ("Current Roster Pitchers", "current_roster_pitchers.csv"),
    ("Current Roster Hitters", "current_roster_hitters.csv"),
    ("All Pitchers", "pitcher_analytics.csv"),
    ("All Hitters", "hitter_analytics.csv"),
]


def load_data():
    data = {}
    for label, filename in SHEETS:
        path = DATA_DIR / filename
        df = pd.read_csv(path).fillna("")
        if label == "All Pitchers":
            df = df[pd.to_numeric(df.get("pitching_score"), errors="coerce").notna()]
        elif label == "All Hitters":
            df = df[pd.to_numeric(df.get("hitter_score"), errors="coerce").notna()]
        data[label] = {
            "columns": list(df.columns),
            "rows": df.to_dict(orient="records"),
        }
    return data


def main():
    payload = json.dumps(load_data(), ensure_ascii=False).replace("</", "<\\/")
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fantasy Baseball Analytics</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7faf9;
      color: #111827;
    }}
    html {{ height: 100%; }}
    body {{ margin: 0; min-height: 100%; }}
    header {{
      position: sticky;
      top: 0;
      z-index: 3;
      background: #ffffff;
      border-bottom: 1px solid #d9e2e1;
      padding: 14px 18px;
    }}
    h1 {{ margin: 0 0 10px; font-size: 18px; }}
    .tabs {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    button {{
      border: 1px solid #cbd5d4;
      background: #eef7f6;
      padding: 8px 10px;
      border-radius: 6px;
      font-weight: 650;
      cursor: pointer;
    }}
    button.active {{ background: #0f766e; color: white; border-color: #0f766e; }}
    main {{ padding: 16px 18px 28px; }}
    .toolbar {{ display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }}
    .filters {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }}
    .filters label {{ display: grid; gap: 4px; font-size: 12px; color: #475569; }}
    input {{
      width: min(420px, 90vw);
      padding: 9px 11px;
      border: 1px solid #cbd5d4;
      border-radius: 6px;
      font-size: 14px;
    }}
    select, .filters input {{
      padding: 8px 9px;
      border: 1px solid #cbd5d4;
      border-radius: 6px;
      font-size: 13px;
      background: white;
      width: 100%;
      box-sizing: border-box;
    }}
    .filter-row {{
      display: grid;
      grid-template-columns: minmax(120px, 1fr) 72px minmax(80px, 1fr) 34px;
      gap: 6px;
      align-items: end;
    }}
    .icon-btn {{
      padding: 8px 0;
      background: #fff7ed;
      border-color: #fed7aa;
    }}
    .add-filter {{ margin-bottom: 12px; }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid #d9e2e1;
      background: white;
      max-height: calc(100vh - 150px);
      -webkit-overflow-scrolling: touch;
    }}
    table {{ border-collapse: collapse; width: max-content; min-width: 100%; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 7px 9px; white-space: nowrap; }}
    th {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #134e4a;
      color: white;
      cursor: pointer;
      text-align: left;
    }}
    th.sorted::after {{ content: " " attr(data-dir); opacity: .9; }}
    th:first-child, td:first-child {{
      position: sticky;
      left: 0;
      z-index: 1;
      max-width: 170px;
      overflow: hidden;
      text-overflow: ellipsis;
      background: white;
      box-shadow: 1px 0 0 #e5e7eb;
    }}
    th:first-child {{
      z-index: 4;
      background: #134e4a;
    }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tr:hover td {{ background: #f0fdfa; }}
    tr:hover td:first-child {{ background: #ecfdf5; }}
    .muted {{ color: #6b7280; font-size: 13px; }}
    td.heat {{ font-weight: 650; }}
    @media (max-width: 720px) {{
      header {{ padding: 10px 10px 8px; }}
      h1 {{ font-size: 16px; margin-bottom: 8px; }}
      .tabs {{
        flex-wrap: nowrap;
        overflow-x: auto;
        padding-bottom: 2px;
        scrollbar-width: thin;
      }}
      .tabs button {{ flex: 0 0 auto; }}
      button {{ padding: 7px 9px; font-size: 12px; }}
      main {{ padding: 10px 10px 18px; }}
      .toolbar {{
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 8px;
        align-items: center;
      }}
      input {{ width: 100%; box-sizing: border-box; font-size: 16px; }}
      .filters {{ grid-template-columns: 1fr; }}
      .filter-row {{
        grid-template-columns: minmax(120px, 1fr) 62px minmax(70px, 1fr) 32px;
      }}
      .add-filter {{ width: 100%; }}
      .table-wrap {{
        max-height: calc(100dvh - 178px);
        border-left: 0;
        border-right: 0;
      }}
      table {{ font-size: 12px; }}
      th, td {{ padding: 6px 7px; }}
      th:first-child, td:first-child {{ max-width: 138px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Fantasy Baseball Analytics</h1>
    <nav class="tabs" id="tabs"></nav>
  </header>
  <main>
    <div class="toolbar">
      <input id="search" placeholder="Filter players or values">
      <span class="muted" id="count"></span>
    </div>
    <div class="filters" id="filters"></div>
    <button class="add-filter" id="add-filter">Add column filter</button>
    <div class="table-wrap" id="table"></div>
  </main>
  <script id="analytics-data" type="application/json">{payload}</script>
  <script>
    const data = JSON.parse(document.getElementById("analytics-data").textContent);
    const tabs = document.getElementById("tabs");
    const tableHost = document.getElementById("table");
    const search = document.getElementById("search");
    const count = document.getElementById("count");
    const filtersHost = document.getElementById("filters");
    const addFilterButton = document.getElementById("add-filter");
    let active = Object.keys(data)[0];
    let sort = {{ column: null, dir: "desc" }};
    let columnFilters = [];
    let heatStats = {{}};

    const heatMetrics = [
      "pitching_score",
      "command_score",
      "whiff_percent",
      "hitter_score",
      "batters_eye_score",
      "barrel_batted_rate"
    ];

    function isNumeric(value) {{
      return value !== "" && value !== null && !Number.isNaN(Number(value));
    }}

    function isHeatColumn(column) {{
      return heatMetrics.some(metric => column === metric || column.startsWith(`${{metric}}_`));
    }}

    function heatMetric(column) {{
      return heatMetrics.find(metric => column === metric || column.startsWith(`${{metric}}_`));
    }}

    function percentile(sorted, pct) {{
      if (!sorted.length) return null;
      const idx = (sorted.length - 1) * pct;
      const lo = Math.floor(idx);
      const hi = Math.ceil(idx);
      if (lo === hi) return sorted[lo];
      return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
    }}

    function computeHeatStats() {{
      heatStats = {{}};
      const values = Object.fromEntries(heatMetrics.map(metric => [metric, []]));
      for (const sheet of Object.values(data)) {{
        for (const col of sheet.columns.filter(isHeatColumn)) {{
          const metric = heatMetric(col);
          for (const row of sheet.rows) {{
            const num = Number(row[col]);
            if (Number.isFinite(num)) values[metric].push(num);
          }}
        }}
      }}
      for (const [metric, vals] of Object.entries(values)) {{
        vals.sort((a, b) => a - b);
        if (!vals.length) continue;
        heatStats[metric] = {{
          low: percentile(vals, 0.10),
          mid: percentile(vals, 0.50),
          high: percentile(vals, 0.90),
        }};
      }}
    }}

    function heatColor(value, col) {{
      const stats = heatStats[heatMetric(col)];
      const num = Number(value);
      if (!stats || !Number.isFinite(num) || stats.low === stats.high) return "";
      const t = Math.max(0, Math.min(1, (num - stats.low) / (stats.high - stats.low)));
      if (t < 0.5) {{
        const p = t / 0.5;
        const r = 252;
        const g = Math.round(165 + (243 - 165) * p);
        const b = Math.round(165 + (199 - 165) * p);
        return `rgb(${{r}}, ${{g}}, ${{b}})`;
      }}
      const p = (t - 0.5) / 0.5;
      const r = Math.round(254 + (134 - 254) * p);
      const g = Math.round(243 + (239 - 243) * p);
      const b = Math.round(199 + (172 - 199) * p);
      return `rgb(${{r}}, ${{g}}, ${{b}})`;
    }}

    function renderTabs() {{
      tabs.innerHTML = "";
      for (const name of Object.keys(data)) {{
        const button = document.createElement("button");
        button.textContent = name;
        button.className = name === active ? "active" : "";
        button.onclick = () => {{
          active = name;
          sort = {{ column: null, dir: "desc" }};
          columnFilters = [];
          search.value = "";
          render();
        }};
        tabs.appendChild(button);
      }}
    }}

    function matchesColumnFilters(row) {{
      return columnFilters.every(filter => {{
        if (!filter.column || filter.value === "") return true;
        const raw = row[filter.column];
        const op = filter.op;
        if (["=", "!="].includes(op)) {{
          const lhs = String(raw ?? "").toLowerCase();
          const rhs = String(filter.value).toLowerCase();
          return op === "=" ? lhs === rhs : lhs !== rhs;
        }}
        const lhs = Number(raw);
        const rhs = Number(filter.value);
        if (!Number.isFinite(lhs) || !Number.isFinite(rhs)) return false;
        if (op === ">=") return lhs >= rhs;
        if (op === "<=") return lhs <= rhs;
        if (op === ">") return lhs > rhs;
        if (op === "<") return lhs < rhs;
        return true;
      }});
    }}

    function sortedRows(rows) {{
      const filter = search.value.trim().toLowerCase();
      let out = filter
        ? rows.filter(row => Object.values(row).some(value => String(value).toLowerCase().includes(filter)))
        : [...rows];
      out = out.filter(matchesColumnFilters);
      if (!sort.column) return out;
      out.sort((a, b) => {{
        const av = a[sort.column], bv = b[sort.column];
        const blankA = av === "" || av === null || av === undefined;
        const blankB = bv === "" || bv === null || bv === undefined;
        if (blankA && blankB) return 0;
        if (blankA) return 1;
        if (blankB) return -1;
        const cmp = isNumeric(av) && isNumeric(bv)
          ? Number(av) - Number(bv)
          : String(av).localeCompare(String(bv));
        return sort.dir === "asc" ? cmp : -cmp;
      }});
      return out;
    }}

    function renderFilters(sheet) {{
      filtersHost.innerHTML = "";
      for (const [index, filter] of columnFilters.entries()) {{
        const row = document.createElement("div");
        row.className = "filter-row";

        const col = document.createElement("select");
        col.innerHTML = `<option value="">Column</option>` + sheet.columns
          .map(c => `<option value="${{c.replaceAll('"', '&quot;')}}" ${{c === filter.column ? "selected" : ""}}>${{c}}</option>`)
          .join("");
        col.onchange = () => {{ columnFilters[index].column = col.value; render(); }};

        const op = document.createElement("select");
        for (const value of [">=", "<=", ">", "<", "=", "!="]) {{
          const option = document.createElement("option");
          option.value = value;
          option.textContent = value;
          option.selected = value === filter.op;
          op.appendChild(option);
        }}
        op.onchange = () => {{ columnFilters[index].op = op.value; render(); }};

        const value = document.createElement("input");
        value.placeholder = "value";
        value.value = filter.value;
        value.oninput = () => {{ columnFilters[index].value = value.value; render(); }};

        const remove = document.createElement("button");
        remove.className = "icon-btn";
        remove.textContent = "x";
        remove.onclick = () => {{ columnFilters.splice(index, 1); render(); }};

        row.append(col, op, value, remove);
        filtersHost.appendChild(row);
      }}
    }}

    function render() {{
      renderTabs();
      const sheet = data[active];
      renderFilters(sheet);
      const rows = sortedRows(sheet.rows);
      count.textContent = `${{rows.length}} rows`;
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      for (const col of sheet.columns) {{
        const th = document.createElement("th");
        th.textContent = col;
        if (sort.column === col) {{
          th.className = "sorted";
          th.dataset.dir = sort.dir === "asc" ? "▲" : "▼";
        }}
        th.onclick = () => {{
          sort = sort.column === col
            ? {{ column: col, dir: sort.dir === "asc" ? "desc" : "asc" }}
            : {{ column: col, dir: "desc" }};
          render();
        }};
        headerRow.appendChild(th);
      }}
      thead.appendChild(headerRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      for (const row of rows) {{
        const tr = document.createElement("tr");
        for (const col of sheet.columns) {{
          const td = document.createElement("td");
          const value = row[col];
          td.textContent = value;
          if (isNumeric(value)) td.className = "num";
          if (isHeatColumn(col) && isNumeric(value)) {{
            td.className = `${{td.className}} heat`.trim();
            td.style.backgroundColor = heatColor(value, col);
          }}
          tr.appendChild(td);
        }}
        tbody.appendChild(tr);
      }}
      table.appendChild(tbody);
      tableHost.innerHTML = "";
      tableHost.appendChild(table);
    }}

    search.addEventListener("input", render);
    addFilterButton.addEventListener("click", () => {{
      columnFilters.push({{ column: "", op: ">=", value: "" }});
      render();
    }});
    computeHeatStats();
    render();
  </script>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()

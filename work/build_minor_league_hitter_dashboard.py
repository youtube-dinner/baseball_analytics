#!/usr/bin/env python3
import json
import math
import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "outputs" / "minor_league_hitter_stars" / "2026"
SOURCE = DATA_DIR / "minor_league_hitters_2026_plus_vs_combined_baseline.csv"
DASHBOARD_CSV = DATA_DIR / "minor_league_hitter_analytics_dashboard.csv"
OUT = ROOT / "outputs" / "Minor_League_Hitter_Analytics.html"
FANTRAX_PLAYERS = ROOT / "outputs" / "fantrax_export" / "fantrax_players_latest.csv"
FANTRAX_ROSTERS = ROOT / "outputs" / "fantrax_export" / "fantrax_rosters_latest.csv"
MY_FANTASY_TEAM = "Bobby and the NitWitts"

BASE_COLUMN_MAP = {
    "Player Name": "Player",
    "Fantasy Roster": "Fantasy Roster",
    "Team": "Team",
    "League Name": "League",
    "League Level": "Level",
    "Age": "Age",
    "G": "G",
    "FGPts_per_game": "FP/G",
    "AB_per_game": "AB/G",
    "Age_Plus": "Age+",
    "FGPts_per_game_Plus": "FG/G+",
    "Approach_score_Plus": "Approach+",
    "Speed_score_Plus": "Speed+",
    "LD%_Plus": "LD%+",
    "HR_FB_pct_Plus": "HR/FB+",
    "wRC+_Score": "wRC+",
    "5 Tool+": "5 Tool+",
    "Hitter+": "Hitter+",
    "Estimated FB": "Est FB",
    "AB": "AB",
    "H": "H",
    "HR": "HR",
    "R": "R",
    "RBI": "RBI",
    "SB": "SB",
    "CS": "CS",
    "BA": "BA",
    "OBP": "OBP",
    "SLP": "SLP",
    "OPS": "OPS",
    "BABIP": "BABIP",
    "BB%": "BB%",
    "K%": "K%",
}

OVERALL_EXTRA_COLUMN_MAP = {
    "LD%": "LD%",
    "GB%": "GB%",
    "FB%": "FB%",
    "IFFB%": "IFFB%",
    "HR/FB%": "HR/FB%",
}

OVERALL_COLUMN_MAP = {**BASE_COLUMN_MAP, **OVERALL_EXTRA_COLUMN_MAP}
ADVANCED_COLUMN_MAP = {
    "PA_advanced": "PA (Adv)",
    "BB%": "BB%",
    "K%": "K%",
    "BB/K": "BB/K",
    "AVG_advanced": "AVG (Adv)",
    "OBP_advanced": "OBP (Adv)",
    "SLG": "SLG (Adv)",
    "OPS_advanced": "OPS (Adv)",
    "ISO": "ISO",
    "Spd": "Spd",
    "BABIP": "BABIP (Adv)",
    "wSB": "wSB",
    "wRC": "wRC",
    "wRAA": "wRAA",
    "wOBA": "wOBA",
    "wRC+": "wRC+ (Adv)",
}
BATTED_COLUMN_MAP = {
    "PA_batted": "PA (Batted)",
    "BABIP_batted": "BABIP (Batted)",
    "GB/FB": "GB/FB",
    "LD%": "LD%",
    "GB%": "GB%",
    "FB%": "FB%",
    "IFFB%": "IFFB%",
    "HR/FB%": "HR/FB%",
    "Pull%": "Pull%",
    "Cent%": "Cent%",
    "Oppo%": "Oppo%",
    "SwStr%": "SwStr%",
    "Balls": "Balls",
    "Strikes": "Strikes",
    "Pitches": "Pitches",
}
HEAT_COLUMNS = [
    "Age+",
    "FG/G+",
    "Approach+",
    "Speed+",
    "LD%+",
    "HR/FB+",
    "wRC+",
    "5 Tool+",
    "Hitter+",
]
RATE_COLUMNS = [
    "BA",
    "OBP",
    "SLP",
    "OPS",
    "BABIP",
    "BB%",
    "K%",
    "BB/K",
    "AVG (Adv)",
    "OBP (Adv)",
    "SLG (Adv)",
    "OPS (Adv)",
    "ISO",
    "BABIP (Adv)",
    "wOBA",
    "BABIP (Batted)",
    "GB/FB",
    "LD%",
    "GB%",
    "FB%",
    "IFFB%",
    "HR/FB%",
    "Pull%",
    "Cent%",
    "Oppo%",
    "SwStr%",
]
ONE_DECIMAL_COLUMNS = HEAT_COLUMNS + ["FP/G", "AB/G", "Est FB"]
ZERO_DECIMAL_COLUMNS = [
    "Age",
    "G",
    "AB",
    "H",
    "HR",
    "R",
    "RBI",
    "SB",
    "CS",
    "PA (Adv)",
    "PA (Batted)",
    "Balls",
    "Strikes",
    "Pitches",
]


def normalize_name(value):
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def name_keys(value):
    normalized = normalize_name(value)
    if not normalized:
        return []
    compact = normalized.replace(" ", "")
    return list(dict.fromkeys([normalized, compact]))


def fantrax_display_name(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if "," not in text:
        return text
    last, first = [part.strip() for part in text.split(",", 1)]
    return f"{first} {last}".strip()


def build_fantrax_roster_lookup():
    player_status = {}
    roster_status = {}
    if FANTRAX_PLAYERS.exists():
        players = pd.read_csv(FANTRAX_PLAYERS)
        for _, row in players.iterrows():
            for key in name_keys(fantrax_display_name(row.get("name"))):
                player_status[key] = row.get("league_status")
    if FANTRAX_ROSTERS.exists():
        rosters = pd.read_csv(FANTRAX_ROSTERS)
        for _, row in rosters.iterrows():
            keys = name_keys(fantrax_display_name(row.get("name")))
            if not keys:
                continue
            label = row.get("team_name")
            status = row.get("roster_status")
            if pd.notna(status) and status:
                label = f"{label} ({status})"
            for key in keys:
                roster_status.setdefault(key, [])
                if label not in roster_status[key]:
                    roster_status[key].append(label)
    return player_status, roster_status


def add_fantasy_roster_column(df):
    player_status, roster_status = build_fantrax_roster_lookup()

    def roster_label(player_name):
        keys = name_keys(player_name)
        for key in keys:
            rostered = roster_status.get(key)
            if rostered:
                return "; ".join(rostered)
        status = None
        for key in keys:
            status = player_status.get(key)
            if status:
                break
        if status == "FA":
            return "Available"
        if status == "WW":
            return "Waivers"
        if status == "T":
            return "Rostered"
        return "Not in Fantrax"

    out = df.copy()
    out["Fantasy Roster"] = out["Player Name"].map(roster_label)
    return out


def clean_number(value, decimals=None):
    if pd.isna(value):
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(num):
        return ""
    if decimals is None:
        return num
    return round(num, decimals)


def existing_column_map(df, column_map):
    return {source: label for source, label in column_map.items() if source in df.columns}


def format_dashboard_frame(df, column_map, sort_cols):
    missing = [col for col in column_map if col not in df.columns]
    if missing:
        raise ValueError(f"Missing dashboard columns: {', '.join(missing)}")
    out = df[list(column_map)].rename(columns=column_map)
    for col in out.columns:
        if col in RATE_COLUMNS:
            out[col] = out[col].map(lambda value: clean_number(value, 3))
        elif col in ONE_DECIMAL_COLUMNS:
            out[col] = out[col].map(lambda value: clean_number(value, 1))
        elif col in ZERO_DECIMAL_COLUMNS:
            out[col] = out[col].map(lambda value: clean_number(value, 0))
        else:
            out[col] = out[col].fillna("")
    sort_cols = [col for col in sort_cols if col in out.columns]
    if sort_cols:
        ascending = [True] * len(sort_cols)
        for metric in ["5 Tool+", "Hitter+", "wRC+", "FG/G+"]:
            if metric in sort_cols:
                ascending[sort_cols.index(metric)] = False
        if "FP/G" in sort_cols:
            ascending[sort_cols.index("FP/G")] = False
        out = out.sort_values(sort_cols, ascending=ascending, kind="stable")
    return out


def load_dashboard_data():
    df = pd.read_csv(SOURCE)
    df = add_fantasy_roster_column(df)
    overall = format_dashboard_frame(df, OVERALL_COLUMN_MAP, ["5 Tool+", "wRC+", "FG/G+"])
    my_players = df[df["Fantasy Roster"].astype(str).str.startswith(MY_FANTASY_TEAM)].copy()
    my_column_map = {
        **BASE_COLUMN_MAP,
        **existing_column_map(df, ADVANCED_COLUMN_MAP),
        **existing_column_map(df, BATTED_COLUMN_MAP),
    }
    my_view = format_dashboard_frame(my_players, my_column_map, ["League", "FP/G"])
    overall.to_csv(DASHBOARD_CSV, index=False)
    my_view.to_csv(DATA_DIR / "minor_league_hitter_analytics_my_players.csv", index=False)
    return {
        "views": {
            "All Players": {
                "columns": list(overall.columns),
                "rows": overall.to_dict(orient="records"),
                "defaultSort": {"column": "5 Tool+", "dir": "desc"},
                "defaultFilters": [{"column": "AB", "op": ">=", "value": "50"}],
            },
            MY_FANTASY_TEAM: {
                "columns": list(my_view.columns),
                "rows": my_view.to_dict(orient="records"),
                "defaultSort": {"column": "League", "dir": "asc", "secondary": "FP/G", "secondaryDir": "desc"},
                "defaultFilters": [],
            },
        },
        "heatColumns": HEAT_COLUMNS,
    }


def main():
    payload = json.dumps(load_dashboard_data(), ensure_ascii=False).replace("</", "<\\/")
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Minor League Hitter Analytics</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f8f7;
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
    h1 {{ margin: 0 0 10px; font-size: 19px; }}
    .tabs {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .tabs button.active {{ background: #14532d; color: white; border-color: #14532d; }}
    main {{ padding: 16px 18px 28px; }}
    .toolbar {{ display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }}
    .filters {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }}
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
    button {{
      border: 1px solid #cbd5d4;
      background: #eef7f6;
      padding: 8px 10px;
      border-radius: 6px;
      font-weight: 650;
      cursor: pointer;
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
      max-height: calc(100vh - 138px);
      -webkit-overflow-scrolling: touch;
    }}
    table {{ border-collapse: collapse; width: max-content; min-width: 100%; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 7px 9px; white-space: nowrap; }}
    th {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #14532d;
      color: white;
      cursor: pointer;
      text-align: left;
    }}
    th.sorted::after {{ content: " " attr(data-dir); opacity: .9; }}
    th:first-child, td:first-child {{
      position: sticky;
      left: 0;
      z-index: 1;
      max-width: 180px;
      overflow: hidden;
      text-overflow: ellipsis;
      background: white;
      box-shadow: 1px 0 0 #e5e7eb;
    }}
    th:first-child {{
      z-index: 4;
      background: #14532d;
    }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tr:hover td {{ background: #f0fdf4; }}
    tr:hover td:first-child {{ background: #ecfdf5; }}
    .muted {{ color: #6b7280; font-size: 13px; }}
    td.heat {{ font-weight: 650; }}
    @media (max-width: 720px) {{
      header {{ padding: 10px 10px 8px; }}
      h1 {{ font-size: 16px; margin-bottom: 8px; }}
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
        max-height: calc(100dvh - 164px);
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
    <h1>Minor League Hitter Analytics</h1>
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
    let active = Object.keys(data.views)[0];
    let sort = {{ ...data.views[active].defaultSort }};
    let columnFilters = (data.views[active].defaultFilters || []).map(filter => {{ return {{ ...filter }}; }});
    let heatStats = {{}};

    function isNumeric(value) {{
      return value !== "" && value !== null && !Number.isNaN(Number(value));
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
      for (const col of data.heatColumns) {{
        const vals = Object.values(data.views)
          .flatMap(view => view.rows.map(row => Number(row[col])).filter(Number.isFinite))
          .sort((a, b) => a - b);
        if (!vals.length) continue;
        heatStats[col] = {{
          low: percentile(vals, 0.10),
          high: percentile(vals, 0.90),
        }};
      }}
    }}

    function heatColor(value, col) {{
      const stats = heatStats[col];
      const num = Number(value);
      if (!stats || !Number.isFinite(num) || stats.low === stats.high) return "";
      const t = Math.max(0, Math.min(1, (num - stats.low) / (stats.high - stats.low)));
      if (t < 0.5) {{
        const p = t / 0.5;
        const r = 254;
        const g = Math.round(202 + (249 - 202) * p);
        const b = Math.round(202 + (215 - 202) * p);
        return `rgb(${{r}}, ${{g}}, ${{b}})`;
      }}
      const p = (t - 0.5) / 0.5;
      const r = Math.round(240 + (134 - 240) * p);
      const g = Math.round(253 + (239 - 253) * p);
      const b = Math.round(244 + (172 - 244) * p);
      return `rgb(${{r}}, ${{g}}, ${{b}})`;
    }}

    function renderTabs() {{
      tabs.innerHTML = "";
      for (const name of Object.keys(data.views)) {{
        const button = document.createElement("button");
        button.textContent = name;
        button.className = name === active ? "active" : "";
        button.onclick = () => {{
          active = name;
          sort = {{ ...data.views[active].defaultSort }};
          columnFilters = (data.views[active].defaultFilters || []).map(filter => {{ return {{ ...filter }}; }});
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
        const primary = compareRows(a, b, sort.column);
        if (primary !== 0) return sort.dir === "asc" ? primary : -primary;
        if (sort.secondary) {{
          const secondary = compareRows(a, b, sort.secondary);
          return sort.secondaryDir === "desc" ? -secondary : secondary;
        }}
        return 0;
      }});
      return out;
    }}

    function compareRows(a, b, column) {{
        const av = a[column], bv = b[column];
        const blankA = av === "" || av === null || av === undefined;
        const blankB = bv === "" || bv === null || bv === undefined;
        if (blankA && blankB) return 0;
        if (blankA) return 1;
        if (blankB) return -1;
        return isNumeric(av) && isNumeric(bv)
          ? Number(av) - Number(bv)
          : String(av).localeCompare(String(bv));
    }}

    function renderFilters() {{
      filtersHost.innerHTML = "";
      for (const [index, filter] of columnFilters.entries()) {{
        const row = document.createElement("div");
        row.className = "filter-row";
        const col = document.createElement("select");
        const view = data.views[active];
        col.innerHTML = `<option value="">Column</option>` + view.columns
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
      renderFilters();
      const view = data.views[active];
      const rows = sortedRows(view.rows);
      count.textContent = `${{rows.length}} rows`;
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      for (const col of view.columns) {{
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
        for (const col of view.columns) {{
          const td = document.createElement("td");
          const value = row[col];
          td.textContent = value;
          if (isNumeric(value)) td.className = "num";
          if (data.heatColumns.includes(col) && isNumeric(value)) {{
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
    print(DASHBOARD_CSV)


if __name__ == "__main__":
    main()

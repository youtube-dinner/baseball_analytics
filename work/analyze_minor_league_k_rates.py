#!/usr/bin/env python3
import html
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "outputs" / "minor_league_hitter_stars"
OUT_DIR = DATA_ROOT / "analysis"
PLAYER_FILES = [
    DATA_ROOT / "2025" / "minor_league_hitters_2025.csv",
    DATA_ROOT / "2026" / "minor_league_hitters_2026.csv",
]


def numeric(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(index=df.index, dtype=float)


def weighted_average(values, weights):
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce")
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return math.nan
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def load_players():
    frames = []
    for path in PLAYER_FILES:
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        frame["Season"] = int(path.parent.name)
        frames.append(frame)
    if not frames:
        raise FileNotFoundError("No player CSVs found.")
    df = pd.concat(frames, ignore_index=True)
    for col in ["K%", "PA", "Age", "LD%", "wRC+", "BB%", "BB/K", "Spd"]:
        if col in df.columns:
            df[col] = numeric(df, col)
    df = df.replace([math.inf, -math.inf], math.nan)
    return df


def build_league_age_summary(df):
    rows = []
    frame = df.dropna(subset=["League Name", "Age", "K%", "PA"]).copy()
    frame["Age Rounded"] = frame["Age"].round().astype(int)
    for (league, level, age), group in frame.groupby(["League Name", "League Level", "Age Rounded"], dropna=False):
        total_pa = numeric(group, "PA").sum()
        if total_pa <= 0:
            continue
        rows.append(
            {
                "League Name": league,
                "League Level": level,
                "Age": age,
                "Players": len(group),
                "Total PA": total_pa,
                "Weighted K%": weighted_average(group["K%"], group["PA"]),
                "Weighted BB%": weighted_average(group["BB%"], group["PA"]),
                "Weighted LD%": weighted_average(group["LD%"], group["PA"]),
                "Weighted wRC+": weighted_average(group["wRC+"], group["PA"]),
            }
        )
    return pd.DataFrame(rows).sort_values(["League Level", "League Name", "Age"], kind="stable")


def build_level_age_summary(df):
    rows = []
    frame = df.dropna(subset=["League Level", "Age", "K%", "PA"]).copy()
    frame["Age Rounded"] = frame["Age"].round().astype(int)
    for (level, age), group in frame.groupby(["League Level", "Age Rounded"], dropna=False):
        total_pa = numeric(group, "PA").sum()
        rows.append(
            {
                "League Level": level,
                "Age": age,
                "Players": len(group),
                "Total PA": total_pa,
                "Weighted K%": weighted_average(group["K%"], group["PA"]),
                "Weighted LD%": weighted_average(group["LD%"], group["PA"]),
                "Weighted wRC+": weighted_average(group["wRC+"], group["PA"]),
            }
        )
    return pd.DataFrame(rows).sort_values(["League Level", "Age"], kind="stable")


def residualize(y, controls):
    y = np.asarray(y, dtype=float)
    x = np.asarray(controls, dtype=float)
    x = np.column_stack([np.ones(len(x)), x])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    return y - x @ coef


def partial_corr(frame, x_col, y_col, control_cols, fixed_effect_col=None):
    use_cols = [x_col, y_col] + control_cols
    if fixed_effect_col:
        use_cols.append(fixed_effect_col)
    data = frame[use_cols].dropna().copy()
    if len(data) < 3:
        return math.nan, len(data)
    controls = []
    for col in control_cols:
        controls.append(numeric(data, col).to_numpy())
    if fixed_effect_col:
        dummies = pd.get_dummies(data[fixed_effect_col], prefix=fixed_effect_col, drop_first=True, dtype=float)
        for col in dummies.columns:
            controls.append(dummies[col].to_numpy())
    control_matrix = np.column_stack(controls) if controls else np.empty((len(data), 0))
    x_resid = residualize(data[x_col], control_matrix)
    y_resid = residualize(data[y_col], control_matrix)
    corr = pd.Series(x_resid).corr(pd.Series(y_resid))
    return corr, len(data)


def build_correlation_summary(df):
    base = df[["K%", "wRC+", "LD%", "Age", "League Name", "League Level", "PA"]].dropna(subset=["K%", "wRC+"]).copy()
    rows = []
    samples = [("All player/league rows", base), ("PA >= 50", base[pd.to_numeric(base["PA"], errors="coerce") >= 50])]
    for sample, frame in samples:
        rows.append(
            {
                "Sample": sample,
                "Comparison": "Raw K% vs wRC+",
                "Correlation": frame["K%"].corr(frame["wRC+"]),
                "N": len(frame),
                "Controls": "None",
            }
        )
        for label, controls, fixed in [
            ("K% vs wRC+, controlling LD%", ["LD%"], None),
            ("K% vs wRC+, controlling LD% + Age", ["LD%", "Age"], None),
            ("K% vs wRC+, controlling LD% + Age + League", ["LD%", "Age"], "League Name"),
            ("K% vs wRC+, controlling LD% + Age + Level", ["LD%", "Age"], "League Level"),
        ]:
            corr, n = partial_corr(frame, "K%", "wRC+", controls, fixed_effect_col=fixed)
            rows.append(
                {
                    "Sample": sample,
                    "Comparison": label,
                    "Correlation": corr,
                    "N": n,
                    "Controls": " + ".join(controls + ([fixed] if fixed else [])),
                }
            )
    return pd.DataFrame(rows)


def build_age_plate_discipline_correlations(df):
    base = df[["Age", "K%", "BB%", "PA", "League Name"]].dropna(subset=["Age", "K%", "BB%", "League Name"]).copy()
    rows = []
    samples = [("All player/league rows", base), ("PA >= 50", base[pd.to_numeric(base["PA"], errors="coerce") >= 50])]
    for sample, frame in samples:
        for metric in ["K%", "BB%"]:
            for controls, label in [([], "League"), (["PA"], "League + PA")]:
                corr, n = partial_corr(frame, "Age", metric, controls, fixed_effect_col="League Name")
                rows.append(
                    {
                        "Sample": sample,
                        "Comparison": f"Age vs {metric}",
                        "Correlation": corr,
                        "N": n,
                        "Controls": label,
                    }
                )
    return pd.DataFrame(rows)


def build_league_age_slope_summary(league_age):
    rows = []
    for (league, level), group in league_age.groupby(["League Name", "League Level"], dropna=False):
        group = group[pd.to_numeric(group["Total PA"], errors="coerce") >= 200].dropna(
            subset=["Age", "Weighted K%", "Weighted BB%"]
        )
        if len(group) < 4:
            continue
        for metric in ["Weighted K%", "Weighted BB%"]:
            slope = np.polyfit(group["Age"], group[metric], 1)[0]
            rows.append(
                {
                    "League Name": league,
                    "League Level": level,
                    "Metric": metric,
                    "Age Slope Per Year": slope,
                    "Age Points": len(group),
                    "Total PA": group["Total PA"].sum(),
                }
            )
    return pd.DataFrame(rows).sort_values(["Metric", "League Level", "League Name"], kind="stable")


def build_k_bucket_summary(df, sample_name="All player/league rows", min_pa=None):
    bins = [0, 0.15, 0.20, 0.25, 0.30, 0.35, math.inf]
    labels = ["<15%", "15-20%", "20-25%", "25-30%", "30-35%", "35%+"]
    frame = df.dropna(subset=["K%", "wRC+", "PA"]).copy()
    if min_pa is not None:
        frame = frame[pd.to_numeric(frame["PA"], errors="coerce") >= min_pa]
    frame["K% Bucket"] = pd.cut(frame["K%"], bins=bins, labels=labels, include_lowest=True, right=False)
    rows = []
    for bucket, group in frame.groupby("K% Bucket", observed=False):
        rows.append(
            {
                "Sample": sample_name,
                "K% Bucket": bucket,
                "Players": len(group),
                "Total PA": numeric(group, "PA").sum(),
                "Median Age": numeric(group, "Age").median(),
                "Weighted K%": weighted_average(group["K%"], group["PA"]),
                "Weighted LD%": weighted_average(group["LD%"], group["PA"]),
                "Weighted wRC+": weighted_average(group["wRC+"], group["PA"]),
            }
        )
    return pd.DataFrame(rows)


def axis_bounds(values):
    values = pd.to_numeric(values, errors="coerce").replace([math.inf, -math.inf], math.nan).dropna()
    if values.empty:
        return 0, 1
    low = values.quantile(0.02)
    high = values.quantile(0.98)
    if not math.isfinite(low) or not math.isfinite(high) or low == high:
        low, high = values.min(), values.max()
    if low == high:
        low -= 1
        high += 1
    pad = (high - low) * 0.06
    return float(low - pad), float(high + pad)


def scale(value, low, high, start, end):
    if pd.isna(value) or high == low:
        return (start + end) / 2
    value = min(max(float(value), low), high)
    return start + (value - low) / (high - low) * (end - start)


def line_svg(summary, x_col, y_col, group_col, title, min_pa=200):
    frame = summary[pd.to_numeric(summary["Total PA"], errors="coerce") >= min_pa].copy()
    width, height = 980, 520
    left, right, top, bottom = 70, 220, 42, 62
    plot_w, plot_h = width - left - right, height - top - bottom
    x_low, x_high = axis_bounds(frame[x_col])
    y_low, y_high = axis_bounds(frame[y_col])
    palette = [
        "#2563eb",
        "#dc2626",
        "#0f766e",
        "#9333ea",
        "#b45309",
        "#be123c",
        "#0891b2",
        "#4d7c0f",
        "#7c3aed",
        "#c2410c",
        "#0f172a",
        "#16a34a",
        "#db2777",
        "#ca8a04",
    ]
    lines = []
    labels = []
    for idx, (name, group) in enumerate(frame.groupby(group_col, dropna=False)):
        group = group.sort_values(x_col)
        coords = []
        for _, row in group.iterrows():
            x = scale(row[x_col], x_low, x_high, left, left + plot_w)
            y = scale(row[y_col], y_low, y_high, top + plot_h, top)
            coords.append(f"{x:.2f},{y:.2f}")
        if len(coords) < 2:
            continue
        color = palette[idx % len(palette)]
        lines.append(f'<polyline points="{" ".join(coords)}" fill="none" stroke="{color}" stroke-width="2.1" opacity="0.9" />')
        labels.append(f'<text x="{left+plot_w+18}" y="{top+18+(idx%22)*19}" fill="{color}" font-size="11">{html.escape(str(name))}</text>')
    return f"""
<svg class="panel" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#fff" />
  <text x="{left}" y="26" font-size="16" font-weight="700">{html.escape(title)}</text>
  <text x="{width-right}" y="26" text-anchor="end" font-size="12" fill="#64748b">Min {min_pa} PA per point</text>
  <line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#94a3b8" />
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#94a3b8" />
  {''.join(lines)}
  {''.join(labels)}
  <text x="{left + plot_w/2}" y="{height-14}" text-anchor="middle" font-size="12">{html.escape(x_col)}</text>
  <text x="16" y="{top + plot_h/2}" transform="rotate(-90 16 {top + plot_h/2})" text-anchor="middle" font-size="12">{html.escape(y_col)}</text>
</svg>"""


def scatter_svg(df, x_col, y_col, title, color="#2563eb"):
    frame = df[[x_col, y_col, "PA"]].apply(pd.to_numeric, errors="coerce").dropna(subset=[x_col, y_col])
    width, height = 720, 420
    left, right, top, bottom = 64, 24, 42, 54
    plot_w, plot_h = width - left - right, height - top - bottom
    x_low, x_high = axis_bounds(frame[x_col])
    y_low, y_high = axis_bounds(frame[y_col])
    points = []
    for _, row in frame.iterrows():
        x = scale(row[x_col], x_low, x_high, left, left + plot_w)
        y = scale(row[y_col], y_low, y_high, top + plot_h, top)
        radius = min(4.2, max(1.7, math.sqrt(max(row.get("PA", 1), 1)) / 6))
        points.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{color}" opacity="0.18" />')
    return f"""
<svg class="panel" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#fff" />
  <text x="{left}" y="26" font-size="16" font-weight="700">{html.escape(title)}</text>
  <text x="{width-right}" y="26" text-anchor="end" font-size="12" fill="#64748b">n={len(frame)}</text>
  <line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#94a3b8" />
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#94a3b8" />
  {''.join(points)}
  <text x="{left + plot_w/2}" y="{height-14}" text-anchor="middle" font-size="12">{html.escape(x_col)}</text>
  <text x="16" y="{top + plot_h/2}" transform="rotate(-90 16 {top + plot_h/2})" text-anchor="middle" font-size="12">{html.escape(y_col)}</text>
</svg>"""


def write_html(league_age, level_age, buckets, correlations, age_correlations, slope_summary, df):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Minor League K% Analysis</title>
  <style>
    body {{ margin: 24px; font-family: Arial, sans-serif; color: #111827; background: #f8fafc; }}
    h1 {{ margin: 0 0 8px; }}
    h2 {{ margin: 28px 0 10px; }}
    p {{ color: #475569; max-width: 980px; line-height: 1.45; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(720px, 1fr)); gap: 16px; align-items: start; }}
    .wide {{ grid-column: 1 / -1; }}
    .panel {{ border: 1px solid #d1d5db; background: #fff; }}
    table {{ border-collapse: collapse; background: #fff; font-size: 13px; margin-bottom: 14px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 6px 8px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #14532d; color: #fff; }}
  </style>
</head>
<body>
  <h1>Minor League K% Analysis</h1>
  <p>Uses completed 2025 rows plus current 2026 rows. League-age and level-age points are PA-weighted. Correlation controls use partial correlations by residualizing K% and wRC+ against the listed controls.</p>
  <div class="grid">
    <div class="wide">{line_svg(league_age, "Age", "Weighted K%", "League Name", "PA-Weighted K% by League and Age")}</div>
    <div class="wide">{line_svg(level_age, "Age", "Weighted K%", "League Level", "PA-Weighted K% by Level and Age", min_pa=500)}</div>
    {scatter_svg(df, "K%", "wRC+", "Player K% vs wRC+", "#dc2626")}
    {scatter_svg(df, "LD%", "wRC+", "Player LD% vs wRC+", "#0f766e")}
  </div>
  <h2>K% Correlations With wRC+</h2>
  {correlations.to_html(index=False, float_format=lambda value: f"{value:.4f}" if isinstance(value, float) else value)}
  <h2>Age Correlations With K% and BB%</h2>
  {age_correlations.to_html(index=False, float_format=lambda value: f"{value:.4f}" if isinstance(value, float) else value)}
  <h2>Within-League Age Slopes</h2>
  <p>Slopes are fitted from PA-weighted league-age buckets with at least 200 PA per age point and at least four age points in the league.</p>
  {slope_summary.to_html(index=False, float_format=lambda value: f"{value:.4f}" if isinstance(value, float) else value)}
  <h2>wRC+ by K% Bucket</h2>
  {buckets.to_html(index=False, float_format=lambda value: f"{value:.4f}" if isinstance(value, float) else value)}
</body>
</html>
"""
    path = OUT_DIR / "minor_league_k_rate_analysis.html"
    path.write_text(html_doc, encoding="utf-8")
    return path


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_players()
    league_age = build_league_age_summary(df)
    level_age = build_level_age_summary(df)
    correlations = build_correlation_summary(df)
    age_correlations = build_age_plate_discipline_correlations(df)
    slope_summary = build_league_age_slope_summary(league_age)
    buckets = pd.concat(
        [
            build_k_bucket_summary(df),
            build_k_bucket_summary(df, sample_name="PA >= 50", min_pa=50),
        ],
        ignore_index=True,
    )
    league_age_path = OUT_DIR / "k_rate_by_league_age.csv"
    level_age_path = OUT_DIR / "k_rate_by_level_age.csv"
    corr_path = OUT_DIR / "k_rate_wrc_correlations.csv"
    age_corr_path = OUT_DIR / "age_k_bb_league_control_correlations.csv"
    slope_path = OUT_DIR / "league_age_k_bb_slopes.csv"
    bucket_path = OUT_DIR / "k_rate_bucket_wrc_summary.csv"
    league_age.to_csv(league_age_path, index=False)
    level_age.to_csv(level_age_path, index=False)
    correlations.to_csv(corr_path, index=False)
    age_correlations.to_csv(age_corr_path, index=False)
    slope_summary.to_csv(slope_path, index=False)
    buckets.to_csv(bucket_path, index=False)
    html_path = write_html(league_age, level_age, buckets, correlations, age_correlations, slope_summary, df)
    print(league_age_path)
    print(level_age_path)
    print(corr_path)
    print(age_corr_path)
    print(slope_path)
    print(bucket_path)
    print(html_path)


if __name__ == "__main__":
    main()

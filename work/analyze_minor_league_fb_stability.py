#!/usr/bin/env python3
import html
import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
YEAR = 2025
DATA_DIR = ROOT / "outputs" / "minor_league_hitter_stars" / str(YEAR)
PLAYERS_CSV = DATA_DIR / f"minor_league_hitters_{YEAR}.csv"
OUT_DIR = DATA_DIR


def numeric(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(index=df.index, dtype=float)


def add_batted_air_metrics(df):
    out = df.copy()
    if "Estimated BIP" not in out.columns and {"AB", "SO", "HR", "SF"}.issubset(out.columns):
        out["Estimated BIP"] = numeric(out, "AB") - numeric(out, "SO") - numeric(out, "HR") + numeric(out, "SF")
        out["Estimated BIP"] = out["Estimated BIP"].where(out["Estimated BIP"] > 0)
    if "Estimated FB" not in out.columns and {"Estimated BIP", "FB%"}.issubset(out.columns):
        out["Estimated FB"] = numeric(out, "Estimated BIP") * numeric(out, "FB%")
    if "Balls_in_Air" not in out.columns and "GB%" in out.columns:
        out["Balls_in_Air"] = 1 - numeric(out, "GB%")
    return out


def safe_divide(numerator, denominator):
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce")
    result = numerator / denominator
    return result.where(denominator != 0)


def weighted_average(values, weights):
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce")
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return math.nan
    return (values[valid] * weights[valid]).sum() / weights[valid].sum()


def plus_score(value, baseline):
    value = pd.to_numeric(value, errors="coerce")
    baseline = pd.to_numeric(baseline, errors="coerce")
    result = value / baseline * 100
    return result.where((baseline != 0) & value.notna() & baseline.notna())


def regress_to_average(plus_values, opportunities, stabilizer=100):
    plus_values = pd.to_numeric(plus_values, errors="coerce").fillna(100)
    opportunities = pd.to_numeric(opportunities, errors="coerce").fillna(0).clip(lower=0)
    reliability = opportunities / (opportunities + stabilizer)
    return 100 + (plus_values - 100) * reliability


def add_backtest_scores(df, stabilizer=100):
    out = df.copy()
    league_col = "Source League ID" if "Source League ID" in out.columns else "League Name"
    if "BB_K_ratio" not in out.columns and {"BB", "SO"}.issubset(out.columns):
        out["BB_K_ratio"] = safe_divide(numeric(out, "BB"), numeric(out, "SO"))
    if "HR_IFFB_ratio" not in out.columns and {"HR/FB%", "IFFB%"}.issubset(out.columns):
        out["HR_IFFB_ratio"] = safe_divide(numeric(out, "HR/FB%"), numeric(out, "IFFB%"))

    baselines = []
    for league, group in out.groupby(league_col, dropna=False):
        baselines.append(
            {
                league_col: league,
                "Baseline LD%": weighted_average(numeric(group, "LD%"), numeric(group, "PA")),
                "Baseline HR/FB%": weighted_average(numeric(group, "HR/FB%"), numeric(group, "PA")),
                "Baseline HR_IFFB_ratio": weighted_average(numeric(group, "HR_IFFB_ratio"), numeric(group, "PA")),
                "Baseline BB_K_ratio": weighted_average(numeric(group, "BB_K_ratio"), numeric(group, "PA")),
            }
        )
    baseline_df = pd.DataFrame(baselines)
    out = out.merge(baseline_df, on=league_col, how="left")

    out["LD%+"] = plus_score(numeric(out, "LD%"), numeric(out, "Baseline LD%")).fillna(100)
    out["HR/FB%+"] = plus_score(numeric(out, "HR/FB%"), numeric(out, "Baseline HR/FB%")).fillna(100)
    out["HR_IFFB_ratio+"] = plus_score(numeric(out, "HR_IFFB_ratio"), numeric(out, "Baseline HR_IFFB_ratio")).fillna(100)
    out["BB_K_ratio+"] = plus_score(numeric(out, "BB_K_ratio"), numeric(out, "Baseline BB_K_ratio")).fillna(100)

    out["LD% Weighted+"] = regress_to_average(out["LD%+"], numeric(out, "Estimated BIP"), stabilizer)
    out["HR/FB% Weighted+"] = regress_to_average(out["HR/FB%+"], numeric(out, "Estimated FB"), stabilizer)
    out["BB/K Weighted+"] = regress_to_average(out["BB_K_ratio+"], numeric(out, "BB") + numeric(out, "SO"), stabilizer)
    out[f"FB Quality+ K={stabilizer}"] = regress_to_average(out["HR_IFFB_ratio+"], numeric(out, "Estimated FB"), stabilizer)
    out["LD + HR/FB Weighted+"] = (out["LD% Weighted+"] + out["HR/FB% Weighted+"]) / 2
    out["LD + HR/FB + BB/K Weighted+"] = (
        out["LD% Weighted+"] + out["HR/FB% Weighted+"] + out["BB/K Weighted+"]
    ) / 3
    return out


def summarize_group(group):
    row = {
        "Players": len(group),
        "Median AB": numeric(group, "AB").median(),
        "Median Estimated FB": numeric(group, "Estimated FB").median(),
        "Total PA": numeric(group, "PA").sum(),
        "Total AB": numeric(group, "AB").sum(),
        "Total Estimated FB": numeric(group, "Estimated FB").sum(),
    }
    for col in ["HR/FB%", "IFFB%", "HR_IFFB_ratio", "FB%", "LD%", "GB%", "Balls_in_Air"]:
        if col in group.columns:
            values = numeric(group, col)
            row[f"{col} Mean"] = values.mean()
            row[f"{col} Median"] = values.median()
            row[f"{col} PA Weighted"] = weighted_average(values, numeric(group, "PA"))
            row[f"{col} Std"] = values.std()
            row[f"{col} IQR"] = values.quantile(0.75) - values.quantile(0.25)
    return pd.Series(row)


def build_bin_summary(df, value_col, bins, labels):
    frame = df.copy()
    frame = frame[pd.to_numeric(frame[value_col], errors="coerce").notna()]
    frame[f"{value_col} Bin"] = pd.cut(frame[value_col], bins=bins, labels=labels, include_lowest=True, right=False)
    return frame.groupby(f"{value_col} Bin", observed=False).apply(summarize_group, include_groups=False).reset_index()


def correlation_summary(df):
    metrics = [
        "LD%",
        "GB%",
        "FB%",
        "Balls_in_Air",
        "HR/FB%",
        "IFFB%",
        "HR_IFFB_ratio",
        "LD% Weighted+",
        "HR/FB% Weighted+",
        "BB/K Weighted+",
        "FB Quality+ K=100",
        "LD + HR/FB Weighted+",
        "LD + HR/FB + BB/K Weighted+",
    ]
    rows = []
    for metric in metrics:
        if metric not in df.columns or "wRC+" not in df.columns:
            continue
        frame = df[[metric, "wRC+", "PA", "AB", "Estimated FB"]].apply(pd.to_numeric, errors="coerce").dropna(subset=[metric, "wRC+"])
        rows.append(
            {
                "Metric": metric,
                "wRC+ Correlation": frame[metric].corr(frame["wRC+"]) if len(frame) >= 2 else math.nan,
                "N": len(frame),
                "Median AB": frame["AB"].median(),
                "Median Estimated FB": frame["Estimated FB"].median(),
            }
        )
    return pd.DataFrame(rows)


def backtest_correlation_summary(df):
    metrics = ["FB Quality+ K=100", "LD + HR/FB Weighted+", "LD + HR/FB + BB/K Weighted+"]
    rows = []
    for metric in metrics:
        frame = df[[metric, "wRC+", "PA", "AB", "Estimated FB", "Estimated BIP"]].apply(pd.to_numeric, errors="coerce")
        frame = frame.dropna(subset=[metric, "wRC+"])
        rows.append(
            {
                "Backtest Metric": metric,
                "wRC+ Correlation": frame[metric].corr(frame["wRC+"]) if len(frame) >= 2 else math.nan,
                "N": len(frame),
                "Median AB": frame["AB"].median(),
                "Median Estimated BIP": frame["Estimated BIP"].median(),
                "Median Estimated FB": frame["Estimated FB"].median(),
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


def scatter_svg(df, x_col, y_col, title, color="#2563eb"):
    frame = df[[x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()
    width, height = 720, 390
    left, right, top, bottom = 64, 24, 42, 54
    plot_w, plot_h = width - left - right, height - top - bottom
    x_low, x_high = axis_bounds(frame[x_col])
    y_low, y_high = axis_bounds(frame[y_col])
    points = []
    for _, row in frame.iterrows():
        x = scale(row[x_col], x_low, x_high, left, left + plot_w)
        y = scale(row[y_col], y_low, y_high, top + plot_h, top)
        points.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2" fill="{color}" opacity="0.22" />')
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


def line_svg(summary, x_col, y_cols, title):
    frame = summary.copy()
    width, height = 720, 390
    left, right, top, bottom = 70, 170, 42, 72
    plot_w, plot_h = width - left - right, height - top - bottom
    xs = range(len(frame))
    y_values = pd.concat([pd.to_numeric(frame[col], errors="coerce") for col in y_cols], ignore_index=True)
    y_low, y_high = axis_bounds(y_values)
    palette = ["#2563eb", "#dc2626", "#0f766e", "#9333ea"]
    lines = []
    labels = []
    for idx, col in enumerate(y_cols):
        coords = []
        for i, value in enumerate(pd.to_numeric(frame[col], errors="coerce")):
            if pd.isna(value):
                continue
            x = left + i / max(1, len(frame) - 1) * plot_w
            y = scale(value, y_low, y_high, top + plot_h, top)
            coords.append(f"{x:.2f},{y:.2f}")
        color = palette[idx % len(palette)]
        lines.append(f'<polyline points="{" ".join(coords)}" fill="none" stroke="{color}" stroke-width="2.4" />')
        labels.append(f'<text x="{left+plot_w+18}" y="{top+18+idx*20}" fill="{color}" font-size="12">{html.escape(col)}</text>')
    ticks = []
    for i, label in enumerate(frame[x_col].astype(str)):
        x = left + i / max(1, len(frame) - 1) * plot_w
        ticks.append(f'<text x="{x:.1f}" y="{height-36}" text-anchor="end" transform="rotate(-35 {x:.1f} {height-36})" font-size="10">{html.escape(label)}</text>')
    return f"""
<svg class="panel" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#fff" />
  <text x="{left}" y="26" font-size="16" font-weight="700">{html.escape(title)}</text>
  <line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#94a3b8" />
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#94a3b8" />
  {''.join(lines)}
  {''.join(labels)}
  {''.join(ticks)}
</svg>"""


def write_html(fb_summary, ab_summary, correlations, backtests, df):
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>2025 Fly-Ball Stability Analysis</title>
  <style>
    body {{ margin: 24px; font-family: Arial, sans-serif; color: #111827; background: #f8fafc; }}
    h1 {{ margin: 0 0 8px; }}
    h2 {{ margin: 28px 0 10px; }}
    p {{ color: #475569; max-width: 900px; line-height: 1.45; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(720px, 1fr)); gap: 16px; }}
    .panel {{ border: 1px solid #d1d5db; background: #fff; }}
    .note {{ background: #fff; border-left: 4px solid #14532d; padding: 10px 14px; max-width: 980px; }}
    table {{ border-collapse: collapse; background: #fff; font-size: 13px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 6px 8px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #14532d; color: #fff; }}
  </style>
</head>
<body>
  <h1>2025 Fly-Ball Stability Analysis</h1>
  <p>Estimated BIP = AB - SO - HR + SF. Estimated FB = Estimated BIP * FB%. Bins use 2025 player/league rows.</p>
  <p class="note">Backtest weighted scores are league-normalized plus metrics regressed toward 100 with K=100. LD% uses Estimated BIP opportunities, HR/FB and FB Quality use Estimated FB opportunities, and BB/K uses BB + SO opportunities.</p>
  <div class="grid">
    {line_svg(fb_summary, "Estimated FB Bin", ["HR/FB% PA Weighted", "IFFB% PA Weighted", "HR_IFFB_ratio PA Weighted"], "Rates by Estimated Fly-Ball Volume")}
    {line_svg(fb_summary, "Estimated FB Bin", ["HR/FB% Std", "IFFB% Std", "HR_IFFB_ratio Std"], "Within-Bin Standard Deviation by Estimated Fly-Ball Volume")}
    {line_svg(ab_summary, "AB Bin", ["FB% PA Weighted", "FB% Std"], "FB% Stability by AB Bin")}
    {scatter_svg(df, "AB", "FB%", "FB% by AB", "#0f766e")}
    {scatter_svg(df, "Balls_in_Air", "wRC+", "Balls in Air vs wRC+", "#7c3aed")}
    {scatter_svg(df, "FB Quality+ K=100", "wRC+", "FB Quality+ K=100 vs wRC+", "#b45309")}
    {scatter_svg(df, "LD + HR/FB Weighted+", "wRC+", "LD + HR/FB Weighted+ vs wRC+", "#0e7490")}
    {scatter_svg(df, "LD + HR/FB + BB/K Weighted+", "wRC+", "LD + HR/FB + BB/K Weighted+ vs wRC+", "#be123c")}
  </div>
  <h2>Backtested Weighted Scores With wRC+</h2>
  {backtests.to_html(index=False, float_format=lambda value: f"{value:.4f}" if isinstance(value, float) else value)}
  <h2>Batted-Ball Correlations With wRC+</h2>
  {correlations.to_html(index=False, float_format=lambda value: f"{value:.4f}" if isinstance(value, float) else value)}
</body>
</html>
"""
    path = OUT_DIR / f"fly_ball_stability_analysis_{YEAR}.html"
    path.write_text(html_doc, encoding="utf-8")
    return path


def main():
    df = pd.read_csv(PLAYERS_CSV)
    df = add_batted_air_metrics(df)
    df = add_backtest_scores(df, stabilizer=100)
    fb_bins = [0, 10, 20, 30, 50, 75, 100, 150, math.inf]
    fb_labels = ["0-9", "10-19", "20-29", "30-49", "50-74", "75-99", "100-149", "150+"]
    ab_bins = [0, 25, 50, 75, 100, 150, 200, 300, math.inf]
    ab_labels = ["0-24", "25-49", "50-74", "75-99", "100-149", "150-199", "200-299", "300+"]
    fb_summary = build_bin_summary(df, "Estimated FB", fb_bins, fb_labels)
    fb_summary_path = OUT_DIR / f"fly_ball_rate_stability_by_estimated_fb_{YEAR}.csv"
    fb_summary.to_csv(fb_summary_path, index=False)
    ab_summary = build_bin_summary(df, "AB", ab_bins, ab_labels)
    ab_summary = ab_summary.rename(columns={"AB Bin": "AB Bin"})
    ab_summary_path = OUT_DIR / f"fb_rate_stability_by_ab_{YEAR}.csv"
    ab_summary.to_csv(ab_summary_path, index=False)
    corr = correlation_summary(df)
    corr_path = OUT_DIR / f"batted_ball_wrc_correlations_{YEAR}.csv"
    corr.to_csv(corr_path, index=False)
    backtests = backtest_correlation_summary(df)
    backtest_path = OUT_DIR / f"weighted_metric_backtest_correlations_{YEAR}.csv"
    backtests.to_csv(backtest_path, index=False)
    score_path = OUT_DIR / f"weighted_metric_backtest_scores_{YEAR}.csv"
    keep_cols = [
        "Player Name",
        "Team",
        "League Name",
        "Source League ID",
        "Age",
        "AB",
        "PA",
        "Estimated BIP",
        "Estimated FB",
        "wRC+",
        "LD% Weighted+",
        "HR/FB% Weighted+",
        "BB/K Weighted+",
        "FB Quality+ K=100",
        "LD + HR/FB Weighted+",
        "LD + HR/FB + BB/K Weighted+",
    ]
    df[[col for col in keep_cols if col in df.columns]].to_csv(score_path, index=False)
    html_path = write_html(fb_summary, ab_summary, corr, backtests, df)
    print(fb_summary_path)
    print(ab_summary_path)
    print(corr_path)
    print(backtest_path)
    print(score_path)
    print(html_path)


if __name__ == "__main__":
    main()

"""
Walk-forward backtest on the held-out 2024 test set.

Uses the same StrikeoutModel wrapper as live inference — one source of truth
for all prediction, edge, and Kelly logic.

Usage:
    cd backend
    python -m train.backtest
"""
import sys
import json
import warnings
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.strikeout import strikeout_model
from app.models.features import FEATURE_COLS

DATA_PATH  = Path("artifacts/test_data.parquet")
OUT_PATH   = Path("artifacts/backtest_results.json")

BANKROLL       = 1000.0
KELLY_FRAC     = 0.25
MIN_EDGE_UNDER = 0.10   # 10% edge required for UNDER picks
MIN_EDGE_OVER  = 0.15   # 15% edge required for OVER picks (higher bar — model overpredicts)


def _safe_feat(v):
    try:
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _row_features(row) -> dict:
    return {
        "k5":           _safe_feat(row.get("k_pct_last5")),
        "k15":          _safe_feat(row.get("k_pct_last15")),
        "ks":           _safe_feat(row.get("k_pct_season")),
        "fip":          _safe_feat(row.get("fip_last15")),
        "ip5":          _safe_feat(row.get("avg_ip_last5")),
        "ff":           _safe_feat(row.get("ff_pct")),
        "velo":         _safe_feat(row.get("ff_velo_avg")),
        "spin":         _safe_feat(row.get("ff_spin_avg")),
        "swstr":        _safe_feat(row.get("swstr_pct")),
        "whiff":        _safe_feat(row.get("whiff_pct")),
        "csw":          _safe_feat(row.get("csw_pct")),
        "opp":          _safe_feat(row.get("opp_k_pct")),
        "lineup_opp":   _safe_feat(row.get("opp_lineup_k_pct")),
        "matchup_score": _safe_feat(row.get("matchup_k_score")),
        "umpire":       _safe_feat(row.get("umpire_k_rate")),
    }


def _net_decimal(odds: int) -> float:
    return 100 / abs(odds) if odds < 0 else odds / 100


def _kelly_bet(prob_win: float, odds: int) -> float:
    b = _net_decimal(odds)
    k = (prob_win * b - (1 - prob_win)) / b
    if k <= 0:
        return 0.0
    return round(min(k * KELLY_FRAC * BANKROLL, BANKROLL), 2)


def run_backtest(data_path: Path = None, out_path: Path = None):
    data_path = data_path or DATA_PATH
    out_path  = out_path  or OUT_PATH

    print("=== mlbet Backtest ===\n")

    if not data_path.exists():
        print(f"No test data at {data_path}. Run train.build_dataset first.")
        return

    strikeout_model.load()

    df = pd.read_parquet(data_path).dropna(subset=["ks_per_start"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    print(f"Test set: {len(df):,} rows")
    print(f"Test period: {df['date'].min().date()} to {df['date'].max().date()}\n")

    lines_path = Path("artifacts/historical_lines.json")
    historical_lines: dict = {}
    if lines_path.exists():
        historical_lines = json.loads(lines_path.read_text())
        print(f"Real lines loaded for {len(historical_lines)} dates.\n")
    else:
        print("No historical lines found. Run train.fetch_historical_lines first.\n")

    records = []
    for _, row in df.iterrows():
        date_str     = row["date"].strftime("%Y-%m-%d")
        pitcher_name = str(row.get("pitcher_name", ""))

        day_lines  = historical_lines.get(date_str, {})
        real_entry = None
        if day_lines and pitcher_name:
            from app.data.odds_api import match_line_to_starter
            real_entry = match_line_to_starter(pitcher_name, day_lines)

        if not real_entry:
            continue

        line       = real_entry["line"]
        over_odds  = real_entry["over_odds"]
        under_odds = real_entry.get("under_odds", -over_odds)

        # Skip rows with no qualifying start history — same gate as live slate
        if pd.isna(row.get("k_pct_last5")) or pd.isna(row.get("k_pct_last15")):
            continue

        feature_row = row[FEATURE_COLS]
        pred = strikeout_model.predict(
            feature_row  = feature_row,
            line         = line,
            over_odds    = over_odds,
            under_odds   = under_odds,
            pitcher_name = pitcher_name,
        )

        if pred.recommendation == "PASS" or pred.confidence == "LOW":
            continue

        edge = abs(pred.edge_pct)
        if pred.recommendation == "UNDER" and edge < MIN_EDGE_UNDER:
            continue
        if pred.recommendation == "OVER"  and edge < MIN_EDGE_OVER:
            continue

        actual = float(row["ks_per_start"])

        if pred.recommendation == "OVER":
            odds     = over_odds
            prob_win = pred.model_prob_over
            win      = actual > line
        else:
            odds     = under_odds
            prob_win = 1 - pred.model_prob_over
            win      = actual < line

        push = actual == line
        bet  = _kelly_bet(prob_win, odds)

        if push or bet == 0:
            outcome, pnl = "PUSH", 0.0
        elif win:
            outcome = "WIN"
            pnl     = round(bet * _net_decimal(odds), 2)
        else:
            outcome = "LOSS"
            pnl     = -bet

        records.append({
            "date":              date_str,
            "pitcher_name":      pitcher_name,
            "mlbam_id":          int(row.get("mlbam_id", 0)),
            "season":            int(row.get("season", 0)),
            "predicted":         pred.predicted_ks,
            "predicted_ks":      pred.predicted_ks,
            "line":              line,
            "actual":            actual,
            "rec":               pred.recommendation,
            "recommendation":    pred.recommendation,
            "edge":              pred.edge_pct,
            "confidence":        pred.confidence,
            "model_prob_over":   pred.model_prob_over,
            "implied_prob_over": pred.implied_prob_over,
            "edge_pct":          pred.edge_pct,
            "bet":               bet,
            "pnl":               pnl,
            "outcome":           outcome,
            "features":          _row_features(row),
        })

    df_r = pd.DataFrame(records)
    wins          = (df_r["outcome"] == "WIN").sum()
    losses        = (df_r["outcome"] == "LOSS").sum()
    pushes        = (df_r["outcome"] == "PUSH").sum()
    total_wagered = df_r["bet"].sum()
    total_pnl     = df_r["pnl"].sum()
    roi           = total_pnl / total_wagered * 100 if total_wagered > 0 else 0
    win_rate      = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0

    print(f"Total bets:    {len(df_r)}")
    print(f"Win / Loss / Push: {wins} / {losses} / {pushes}")
    print(f"Win rate:      {win_rate:.1f}%")
    print(f"Total wagered: ${total_wagered:,.2f}")
    print(f"Total P&L:     ${total_pnl:,.2f}")
    print(f"ROI:           {roi:+.1f}%")

    by_tier = {}
    for tier in ["HIGH", "MEDIUM", "LOW"]:
        t = df_r[df_r["confidence"] == tier]
        if t.empty:
            continue
        tw = (t["outcome"] == "WIN").sum()
        tl = (t["outcome"] == "LOSS").sum()
        tw_amt = t["bet"].sum()
        tp     = t["pnl"].sum()
        by_tier[tier] = {
            "bets":    int(len(t)),
            "wins":    int(tw),
            "losses":  int(tl),
            "winRate": f"{tw / max(tw + tl, 1) * 100:.1f}%",
            "roi":     f"{tp / tw_amt * 100:+.1f}%" if tw_amt > 0 else "0.0%",
            "pnl":     round(float(tp), 2),
        }
        print(f"  {tier}: {len(t)} bets, {by_tier[tier]['winRate']} win, {by_tier[tier]['roi']} ROI")

    df_r["month"] = pd.to_datetime(df_r["date"]).dt.to_period("M")
    monthly = []
    for period, grp in df_r.groupby("month"):
        w = (grp["outcome"] == "WIN").sum()
        l = (grp["outcome"] == "LOSS").sum()
        wag = grp["bet"].sum()
        pnl = grp["pnl"].sum()
        monthly.append({
            "month":  str(period),
            "bets":   int(len(grp)),
            "wins":   int(w),
            "losses": int(l),
            "roi":    round(float(pnl / wag * 100) if wag > 0 else 0, 1),
            "pnl":    round(float(pnl), 2),
        })

    cumulative = df_r.sort_values("date")["pnl"].cumsum().round(2).tolist()
    records_out = df_r.drop(columns=["month"]).to_dict("records")

    results = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "test_rows":    len(df_r),
        "bankroll":     BANKROLL,
        "kelly_frac":   KELLY_FRAC,
        "min_edge_under": MIN_EDGE_UNDER,
        "min_edge_over":  MIN_EDGE_OVER,
        "overall": {
            "bets":    len(df_r),
            "wins":    int(wins),
            "losses":  int(losses),
            "pushes":  int(pushes),
            "winRate": f"{win_rate:.1f}%",
            "roi":     f"{roi:+.1f}%",
            "pnl":     round(float(total_pnl), 2),
            "wagered": round(float(total_wagered), 2),
            "units":   f"{total_pnl / BANKROLL:+.2f}u",
        },
        "byTier":         by_tier,
        "monthly":        monthly,
        "cumulative_pnl": cumulative,
        "records":        records_out,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out_path}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", type=str, default=None, help="Override test data parquet path")
    parser.add_argument("--out-path",  type=str, default=None, help="Override results JSON output path")
    args = parser.parse_args()
    run_backtest(
        data_path=Path(args.data_path) if args.data_path else None,
        out_path=Path(args.out_path)   if args.out_path  else None,
    )

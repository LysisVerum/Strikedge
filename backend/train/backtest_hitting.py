"""
Backtest the hitting model on held-out test data (2025).

No odds API needed — evaluates prediction accuracy only:
  - Overall MAE (predicted hits vs actual hits)
  - Per-game MAE breakdown
  - Distribution of errors
  - Simulated edge detection using DK-style lines (0.5 / 1.5 / 2.5)

Results saved to:
  artifacts/hitting_backtest.json   — full per-game records
  artifacts/strikedge.db            — hitting_predictions table

Usage:
    cd backend
    python -m train.backtest_hitting

    Flags:
      --test-path  artifacts/hitting_test.parquet   (override)
      --out-path   artifacts/hitting_backtest.json  (override)
      --line       1.5   (DK line to evaluate edge against, default 1.5)
"""
import sys
import json
import sqlite3
import warnings
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.hitting import hitting_model, HITTING_FEATURE_COLS

TEST_PATH  = Path("artifacts/hitting_test.parquet")
OUT_PATH   = Path("artifacts/hitting_backtest.json")
DB_PATH    = Path("artifacts/strikedge.db")

# DK-style lines to evaluate (no real odds — synthetic 50/50 implied prob)
_DK_LINES       = [0.5, 1.5, 2.5]
_DEFAULT_LINE   = 1.5
_OVER_THRESHOLD = 0.15   # 15% edge required for OVER
_UNDER_THRESHOLD = 0.10  # 10% edge required for UNDER


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS hitting_predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    batter_id       INTEGER,
    game_pk         INTEGER,
    season          INTEGER,
    predicted_hits  REAL,
    actual_hits     REAL,
    line            REAL,
    model_prob_over REAL,
    edge_pct        REAL,
    recommendation  TEXT,
    confidence      TEXT,
    abs_error       REAL,
    squared_error   REAL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hp_date    ON hitting_predictions(date);
CREATE INDEX IF NOT EXISTS idx_hp_batter  ON hitting_predictions(batter_id);
CREATE INDEX IF NOT EXISTS idx_hp_season  ON hitting_predictions(season);
"""


def _init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_CREATE_TABLE)
    conn.commit()
    return conn


def _insert_records(conn: sqlite3.Connection, records: list[dict]):
    rows = [
        (
            r["date"],
            r.get("batter_id"),
            r.get("game_pk"),
            r.get("season"),
            r["predicted_hits"],
            r["actual_hits"],
            r["line"],
            r["model_prob_over"],
            r["edge_pct"],
            r["recommendation"],
            r["confidence"],
            r["abs_error"],
            r["squared_error"],
        )
        for r in records
    ]
    conn.executemany("""
        INSERT INTO hitting_predictions
            (date, batter_id, game_pk, season, predicted_hits, actual_hits, line,
             model_prob_over, edge_pct, recommendation, confidence, abs_error, squared_error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

def run_backtest(
    test_path: Path = None,
    out_path: Path = None,
    dk_line: float = _DEFAULT_LINE,
    db_path: Path = None,
):
    test_path = test_path or TEST_PATH
    out_path  = out_path  or OUT_PATH
    db_path   = db_path   or DB_PATH

    print("=== StrikeEdge Hitting Backtest ===\n")

    if not test_path.exists():
        print(f"No test data at {test_path}.")
        print("Run: python -m train.build_hitting_dataset --test-only")
        return

    hitting_model.load()

    df = pd.read_parquet(test_path).dropna(subset=["hits_in_game"])
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)

    print(f"Test set:    {len(df):,} batter-games")
    print(f"Test period: {df['game_date'].min().date()} → {df['game_date'].max().date()}")
    print(f"Unique batters: {df['batter_id'].nunique()}")
    print(f"Line evaluated: {dk_line} hits\n")

    records = []
    errors  = []

    for _, row in df.iterrows():
        feat_row = row.reindex(HITTING_FEATURE_COLS)
        if feat_row.isna().all():
            continue

        pred = hitting_model.predict(
            feature_row = feat_row,
            line        = dk_line,
            over_odds   = -115,
            under_odds  = -115,
        )

        actual     = float(row["hits_in_game"])
        abs_err    = abs(pred.predicted_hits - actual)
        sq_err     = (pred.predicted_hits - actual) ** 2
        errors.append(abs_err)

        records.append({
            "date":            row["game_date"].strftime("%Y-%m-%d"),
            "batter_id":       int(row.get("batter_id", 0)),
            "game_pk":         int(row.get("game_pk", 0)),
            "season":          int(row.get("season", 0)),
            "predicted_hits":  pred.predicted_hits,
            "actual_hits":     actual,
            "line":            dk_line,
            "model_prob_over": pred.model_prob_over,
            "edge_pct":        pred.edge_pct,
            "recommendation":  pred.recommendation,
            "confidence":      pred.confidence,
            "abs_error":       round(abs_err, 4),
            "squared_error":   round(sq_err, 4),
        })

    if not records:
        print("No predictions generated.")
        return

    df_r = pd.DataFrame(records)
    mae  = float(np.mean(errors))
    rmse = float(np.sqrt(np.mean(np.array(errors) ** 2)))

    print("=" * 50)
    print(f"Overall MAE:  {mae:.4f} hits/game")
    print(f"Overall RMSE: {rmse:.4f} hits/game")
    print(f"Total rows:   {len(df_r):,}")

    # Error distribution
    err_arr = np.array(errors)
    print(f"\nError distribution:")
    print(f"  within 0.25: {(err_arr <= 0.25).mean():.1%}")
    print(f"  within 0.50: {(err_arr <= 0.50).mean():.1%}")
    print(f"  within 1.00: {(err_arr <= 1.00).mean():.1%}")
    print(f"  > 1.00:      {(err_arr > 1.00).mean():.1%}")

    # By season
    print("\nMAE by season:")
    by_season = {}
    for season, grp in df_r.groupby("season"):
        s_mae = grp["abs_error"].mean()
        s_n   = len(grp)
        by_season[int(season)] = {"mae": round(float(s_mae), 4), "n": int(s_n)}
        print(f"  {season}: MAE={s_mae:.4f}  ({s_n:,} games)")

    # By month
    df_r["month"] = pd.to_datetime(df_r["date"]).dt.to_period("M")
    print("\nMAE by month:")
    monthly = []
    for period, grp in df_r.groupby("month"):
        m_mae = grp["abs_error"].mean()
        monthly.append({"month": str(period), "mae": round(float(m_mae), 4), "n": int(len(grp))})
        print(f"  {period}: MAE={m_mae:.4f}  ({len(grp):,} games)")

    # Edge pick accuracy (OVER/UNDER vs actual outcome)
    edge_picks = df_r[df_r["recommendation"] != "PASS"].copy()
    if not edge_picks.empty:
        edge_picks["correct_over"]  = (
            (edge_picks["recommendation"] == "OVER") &
            (edge_picks["actual_hits"] > edge_picks["line"])
        )
        edge_picks["correct_under"] = (
            (edge_picks["recommendation"] == "UNDER") &
            (edge_picks["actual_hits"] <= edge_picks["line"])
        )
        edge_picks["correct"] = edge_picks["correct_over"] | edge_picks["correct_under"]

        print(f"\nEdge pick accuracy (line={dk_line}):")
        print(f"  Total edge picks: {len(edge_picks)}")
        print(f"  Overall win rate: {edge_picks['correct'].mean():.1%}")

        for rec in ["OVER", "UNDER"]:
            sub = edge_picks[edge_picks["recommendation"] == rec]
            if not sub.empty:
                wr = sub["correct"].mean()
                print(f"  {rec}: {len(sub)} picks, {wr:.1%} win rate, MAE={sub['abs_error'].mean():.4f}")

        by_confidence = {}
        for tier in ["HIGH", "MEDIUM", "LOW"]:
            t = edge_picks[edge_picks["confidence"] == tier]
            if not t.empty:
                by_confidence[tier] = {
                    "n":        int(len(t)),
                    "win_rate": round(float(t["correct"].mean()), 4),
                    "mae":      round(float(t["abs_error"].mean()), 4),
                }
                print(f"  {tier}: {len(t)} picks, "
                      f"{by_confidence[tier]['win_rate']:.1%} win, "
                      f"MAE={by_confidence[tier]['mae']:.4f}")
    else:
        by_confidence = {}
        print(f"\nNo edge picks at line={dk_line} with current thresholds.")

    # Per-line simulation across all DK lines
    print(f"\nSimulated win rate by line:")
    line_results = {}
    for line in _DK_LINES:
        over_correct  = (df_r["actual_hits"] > line).mean()
        under_correct = (df_r["actual_hits"] <= line).mean()
        # Model's predicted over prob vs actual
        feat_series_list = []
        for _, row in df.head(min(500, len(df))).iterrows():
            f = row.reindex(HITTING_FEATURE_COLS)
            if not f.isna().all():
                p = hitting_model.predict(f, line=line)
                feat_series_list.append(p.model_prob_over)
        mean_model_over = np.mean(feat_series_list) if feat_series_list else 0.5
        line_results[str(line)] = {
            "actual_over_rate":  round(float(over_correct), 4),
            "model_prob_over":   round(float(mean_model_over), 4),
        }
        print(f"  {line}: actual over={over_correct:.1%}, model avg P(over)={mean_model_over:.1%}")

    # Save to SQLite
    try:
        conn = _init_db(db_path)
        _insert_records(conn, records)
        conn.close()
        print(f"\nResults inserted into SQLite: {db_path}")
    except Exception as e:
        print(f"\nSQLite write failed: {e}")

    # Save full results JSON
    results = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "test_rows":    len(df_r),
        "line":         dk_line,
        "overall": {
            "mae":  round(mae, 5),
            "rmse": round(rmse, 5),
            "n":    len(df_r),
        },
        "error_distribution": {
            "within_0.25": round(float((err_arr <= 0.25).mean()), 4),
            "within_0.50": round(float((err_arr <= 0.50).mean()), 4),
            "within_1.00": round(float((err_arr <= 1.00).mean()), 4),
            "over_1.00":   round(float((err_arr  > 1.00).mean()), 4),
        },
        "by_season":    by_season,
        "by_month":     monthly,
        "by_confidence": by_confidence,
        "by_line":      line_results,
        "records":      df_r.drop(columns=["month"]).to_dict("records"),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Results saved: {out_path}")
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-path", type=str, default=None)
    parser.add_argument("--out-path",  type=str, default=None)
    parser.add_argument("--line",      type=float, default=_DEFAULT_LINE,
                        help="DK line to evaluate edge picks against (default 1.5)")
    parser.add_argument("--db-path",   type=str, default=None)
    args = parser.parse_args()

    run_backtest(
        test_path = Path(args.test_path) if args.test_path else None,
        out_path  = Path(args.out_path)  if args.out_path  else None,
        dk_line   = args.line,
        db_path   = Path(args.db_path)   if args.db_path   else None,
    )

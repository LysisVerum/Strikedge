"""
Side-by-side comparison of the production XGBoost model vs the experimental
Random Forest model on the held-out test set.

Usage:
    cd backend
    python -m train.compare_models

Requires both models to already be trained:
    python -m train.train_strikeout       -> artifacts/strikeout_model.joblib
    python -m train.train_strikeout_rf    -> artifacts/strikeout_model_rf.joblib
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from scipy import stats
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.models.features import FEATURE_COLS

XGB_PATH  = Path("artifacts/strikeout_model.joblib")
RF_PATH   = Path("artifacts/strikeout_model_rf.joblib")
TEST_PATH = Path("artifacts/test_data.parquet")

# Betting sim parameters (mirror production thresholds)
MIN_EDGE_UNDER = 0.10
MIN_EDGE_OVER  = 0.15
BANKROLL       = 1000.0
KELLY_FRAC     = 0.25
DEFAULT_ODDS   = -115


def _implied_prob(odds: int) -> float:
    return abs(odds) / (abs(odds) + 100) if odds < 0 else 100 / (odds + 100)


def _net_return(odds: int) -> float:
    return 100 / abs(odds) if odds < 0 else odds / 100


def _kelly_bet(p_win: float, odds: int, bankroll: float = BANKROLL) -> float:
    implied = _implied_prob(odds)
    net = _net_return(odds)
    edge = p_win - implied
    if edge <= 0:
        return 0.0
    k = (edge / net) * KELLY_FRAC
    return round(min(k * bankroll, bankroll * 0.10), 2)


def simulate_betting(y_true, y_pred, residual_std, line_col=None):
    """
    For each game, simulate: if we had bet this, what would the outcome be?
    Uses the same normal-CDF probability logic as the production strikeout model.
    Line defaults to y_pred rounded to nearest 0.5.
    """
    from scipy.stats import norm

    results = []
    for actual, predicted in zip(y_true, y_pred):
        line = round(predicted * 2) / 2  # nearest 0.5
        line = max(3.5, min(line, 12.5))

        prob_over  = 1 - norm.cdf(line, loc=predicted, scale=residual_std)
        prob_under = norm.cdf(line, loc=predicted, scale=residual_std)
        implied    = _implied_prob(DEFAULT_ODDS)

        edge_over  = prob_over  - implied
        edge_under = prob_under - implied

        # Only take bets meeting edge thresholds
        if edge_over >= MIN_EDGE_OVER:
            side = "OVER"
            p_win = prob_over
            edge  = edge_over
        elif edge_under >= MIN_EDGE_UNDER:
            side = "UNDER"
            p_win = prob_under
            edge  = edge_under
        else:
            continue

        bet = _kelly_bet(p_win, DEFAULT_ODDS)
        if bet <= 0:
            continue

        net = _net_return(DEFAULT_ODDS)
        if side == "OVER":
            won = actual > line
        else:
            won = actual < line

        pnl = round(bet * net, 2) if won else -bet
        results.append({"side": side, "edge": edge, "bet": bet, "won": won, "pnl": pnl})

    return results


def betting_summary(results: list[dict]) -> dict:
    if not results:
        return {"bets": 0}
    wins  = sum(1 for r in results if r["won"])
    total_bet = sum(r["bet"] for r in results)
    total_pnl = sum(r["pnl"] for r in results)
    return {
        "bets":     len(results),
        "wins":     wins,
        "losses":   len(results) - wins,
        "win_rate": round(wins / len(results) * 100, 1),
        "wagered":  round(total_bet, 2),
        "pnl":      round(total_pnl, 2),
        "roi":      round(total_pnl / total_bet * 100, 1) if total_bet > 0 else 0,
        "avg_edge": round(np.mean([r["edge"] for r in results]) * 100, 1),
    }


def evaluate_model(name: str, pipeline, X_test, y_test, metrics_path: Path = None):
    y_pred = pipeline.predict(X_test)
    residuals = y_test - y_pred
    test_mae = mean_absolute_error(y_test, y_pred)
    res_std  = float(np.std(residuals))

    within_1 = np.mean(np.abs(residuals) <= 1.0) * 100
    within_2 = np.mean(np.abs(residuals) <= 2.0) * 100

    # Load saved CV MAE if available
    cv_mae = cv_std = None
    if metrics_path and metrics_path.exists():
        m = json.loads(metrics_path.read_text())
        cv_mae = m.get("cv_mae")
        cv_std = m.get("cv_mae_std")

    bet_results = simulate_betting(y_test, y_pred, res_std)
    bets = betting_summary(bet_results)

    return {
        "name":      name,
        "test_mae":  round(test_mae, 3),
        "res_std":   round(res_std, 3),
        "within_1":  round(within_1, 1),
        "within_2":  round(within_2, 1),
        "cv_mae":    cv_mae,
        "cv_std":    cv_std,
        "betting":   bets,
        "y_pred":    y_pred,
    }


def print_report(a: dict, b: dict):
    def col(val, better, worse, fmt=".3f"):
        s = f"{val:{fmt}}" if isinstance(val, float) else str(val)
        if val == better:
            return f"\033[92m{s}\033[0m"   # green
        if val == worse:
            return f"\033[91m{s}\033[0m"   # red
        return s

    print("\n" + "=" * 60)
    print(f"  MODEL COMPARISON  —  held-out test set ({len(a['y_pred']):,} starts)")
    print("=" * 60)
    print(f"{'Metric':<28} {'XGBoost':>12} {'Random Forest':>14}")
    print("-" * 60)

    # Accuracy metrics (lower is better)
    for label, ka, kb in [
        ("CV MAE (train)",   "cv_mae", "cv_mae"),
        ("Test MAE",         "test_mae", "test_mae"),
        ("Residual std",     "res_std", "res_std"),
    ]:
        va, vb = a.get(ka), b.get(kb)
        if va is None or vb is None:
            print(f"  {label:<26} {'N/A':>12} {'N/A':>14}")
            continue
        better_val = min(va, vb)
        worse_val  = max(va, vb)
        print(f"  {label:<26} {col(va, better_val, worse_val):>20} {col(vb, better_val, worse_val):>22}")

    # Within-N accuracy (higher is better)
    for label, ka, kb in [
        ("Within 1 K (%)",   "within_1", "within_1"),
        ("Within 2 K (%)",   "within_2", "within_2"),
    ]:
        va, vb = a.get(ka), b.get(kb)
        if va is None or vb is None:
            continue
        better_val = max(va, vb)
        worse_val  = min(va, vb)
        print(f"  {label:<26} {col(va, better_val, worse_val, '.1f'):>20} {col(vb, better_val, worse_val, '.1f'):>22}")

    print("-" * 60)
    print("  SIMULATED BETTING (test set, Kelly 25%, -115 default odds)")
    print("-" * 60)

    ba, bb = a["betting"], b["betting"]
    if ba.get("bets", 0) == 0 and bb.get("bets", 0) == 0:
        print("  No bets triggered at current thresholds.")
    else:
        for label, ka, kb, higher_better in [
            ("Bets placed",   "bets",     "bets",     None),
            ("Win rate (%)",  "win_rate", "win_rate", True),
            ("ROI (%)",       "roi",      "roi",      True),
            ("PnL ($)",       "pnl",      "pnl",      True),
            ("Avg edge (%)",  "avg_edge", "avg_edge", True),
        ]:
            va = ba.get(ka, "N/A")
            vb = bb.get(ka, "N/A")
            if higher_better is None:
                print(f"  {label:<26} {str(va):>12} {str(vb):>14}")
            elif isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                best  = max(va, vb) if higher_better else min(va, vb)
                worst = min(va, vb) if higher_better else max(va, vb)
                fmt = ".1f" if isinstance(va, float) else "d"
                print(f"  {label:<26} {col(va, best, worst, fmt):>20} {col(vb, best, worst, fmt):>22}")

    print("\n" + "=" * 60)


def main():
    for path, label in [(XGB_PATH, "XGBoost"), (RF_PATH, "Random Forest"), (TEST_PATH, "test data")]:
        if not path.exists():
            print(f"ERROR: {path} not found.")
            if "rf" in str(path):
                print("  Run: python -m train.train_strikeout_rf")
            elif "xgb" in str(path) or "strikeout_model.j" in str(path):
                print("  Run: python -m train.train_strikeout")
            else:
                print("  Run: python -m train.build_dataset")
            sys.exit(1)

    df_test = pd.read_parquet(TEST_PATH)
    X_test  = df_test[FEATURE_COLS]
    y_test  = df_test["ks_per_start"].values
    print(f"Test set: {len(df_test):,} starts  "
          f"(seasons: {sorted(df_test['season'].unique().tolist()) if 'season' in df_test.columns else 'unknown'})")

    xgb_pipe = joblib.load(XGB_PATH)
    rf_pipe  = joblib.load(RF_PATH)

    print("Evaluating XGBoost model...")
    xgb_result = evaluate_model("XGBoost", xgb_pipe, X_test, y_test,
                                 Path("artifacts/strikeout_model_metrics.json"))

    print("Evaluating Random Forest model...")
    rf_result  = evaluate_model("Random Forest", rf_pipe, X_test, y_test,
                                Path("artifacts/strikeout_model_rf_metrics.json"))

    print_report(xgb_result, rf_result)

    # Wilcoxon signed-rank test on absolute errors
    err_xgb = np.abs(xgb_result["y_pred"] - y_test)
    err_rf  = np.abs(rf_result["y_pred"]  - y_test)
    stat, p = stats.wilcoxon(err_xgb, err_rf)
    winner = "Random Forest" if err_rf.mean() < err_xgb.mean() else "XGBoost"
    sig = "significant" if p < 0.05 else "not significant"
    print(f"\n  Wilcoxon test: {winner} lower errors, p={p:.4f} ({sig})")
    print(f"  MAE difference: {abs(err_xgb.mean() - err_rf.mean()):.3f} Ks/start")
    print("=" * 60)

    if winner == "Random Forest" and p < 0.05:
        print("\n  VERDICT: Random Forest wins significantly.")
        print("  To promote it to production:")
        print("    cp artifacts/strikeout_model_rf.joblib artifacts_seed/strikeout_model.joblib")
        print("    cp artifacts/strikeout_model_rf_metrics.json artifacts_seed/strikeout_model_metrics.json")
        print("  Then redeploy to Railway.")
    elif winner == "XGBoost" and p < 0.05:
        print("\n  VERDICT: XGBoost wins significantly. Keep current model.")
    else:
        print("\n  VERDICT: No significant difference. Keep current model (XGBoost) in production.")


if __name__ == "__main__":
    main()

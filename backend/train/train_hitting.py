"""
Train the hitting prop XGBoost model.

Usage:
    cd backend
    python -m train.train_hitting

Uses artifacts/hitting_train.parquet if present (built by build_hitting_dataset.py).
Falls back to calibrated synthetic data so the model is always trainable.

To build the real dataset first:
    python -m train.build_hitting_dataset
    python -m train.train_hitting
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import cross_val_score, KFold
from sklearn.metrics import mean_absolute_error
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression
import xgboost as xgb

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.hitting import HITTING_FEATURE_COLS

ARTIFACT_PATH = Path("artifacts/hitting_model.joblib")
METRICS_PATH  = Path("artifacts/hitting_model_metrics.json")


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------

def _generate_synthetic_data(n_rows: int = 12_000, seed: int = 42) -> pd.DataFrame:
    """
    Generate realistic batter-game rows.

    Calibrated from 2019–2024 MLB Statcast:
    - League BA: ~0.248
    - Average PAs per game: ~4.1
    - Expected hits per game: ~1.02
    - Hit distribution: ~0H 37%, 1H 37%, 2H 18%, 3H+ 8%
    - Barrel rate: ~6.5% of batted balls
    - Hard hit%: ~38% of batted balls
    - Exit velocity: ~88 mph
    """
    rng = np.random.default_rng(seed)
    n = n_rows

    # Batter latent talent
    talent = rng.normal(0, 1, n)

    h_per_pa_season = np.clip(0.248 + 0.038 * talent + rng.normal(0, 0.018, n), 0.100, 0.400)
    h_per_pa_last30 = np.clip(h_per_pa_season + rng.normal(0, 0.038, n), 0.050, 0.500)
    h_per_pa_last14 = np.clip(h_per_pa_last30 + rng.normal(0, 0.055, n), 0.000, 0.600)
    h_per_pa_last7  = np.clip(h_per_pa_last14 + rng.normal(0, 0.075, n), 0.000, 0.700)

    barrel_rate_last30    = np.clip(0.065 + 0.028 * talent + rng.normal(0, 0.018, n), 0.000, 0.200)
    hard_hit_pct_last30   = np.clip(0.380 + 0.090 * talent + rng.normal(0, 0.055, n), 0.100, 0.700)
    xba_last30            = np.clip(0.250 + 0.038 * talent + rng.normal(0, 0.022, n), 0.100, 0.450)
    avg_exit_velo_last30  = np.clip(88.0  + 3.5  * talent + rng.normal(0, 2.0, n), 78.0, 100.0)
    sweet_spot_pct_last30 = np.clip(0.330 + 0.035 * talent + rng.normal(0, 0.038, n), 0.150, 0.550)

    pa_per_game_last14       = np.clip(4.1 + 0.45 * talent + rng.normal(0, 0.30, n), 2.0, 5.5)
    h_per_pa_vs_hand_last60  = np.clip(h_per_pa_season + rng.normal(0, 0.038, n), 0.000, 0.600)

    # Opponent pitcher quality (independent of batter talent)
    opp_k_pct               = np.clip(rng.normal(0.228, 0.040, n), 0.100, 0.380)
    opp_hard_hit_pct_allowed = np.clip(rng.normal(0.380, 0.048, n), 0.200, 0.600)
    opp_xba_allowed          = np.clip(rng.normal(0.248, 0.030, n), 0.150, 0.380)

    park_factor = np.clip(rng.normal(1.00, 0.075, n), 0.80, 1.25)
    is_home     = rng.integers(0, 2, n).astype(float)

    # Target construction
    # True BA adjusted for context
    true_ba = h_per_pa_last30.copy()
    true_ba = true_ba * park_factor
    # Tough pitcher reduces BA — opponent xBA allowed vs league avg (0.248)
    true_ba = true_ba * (1 - 0.25 * (0.248 - opp_xba_allowed) / 0.030)
    # Hard-hit quality boost
    true_ba = true_ba * (1 + 0.08 * (avg_exit_velo_last30 - 88) / 3.5)
    true_ba = np.clip(true_ba, 0.02, 0.65)

    expected_hits = true_ba * pa_per_game_last14
    hits = rng.poisson(expected_hits).astype(float)
    hits = np.clip(hits, 0, 6)

    return pd.DataFrame({
        "h_per_pa_last7":             h_per_pa_last7,
        "h_per_pa_last14":            h_per_pa_last14,
        "h_per_pa_last30":            h_per_pa_last30,
        "h_per_pa_season":            h_per_pa_season,
        "barrel_rate_last30":         barrel_rate_last30,
        "hard_hit_pct_last30":        hard_hit_pct_last30,
        "xba_last30":                 xba_last30,
        "avg_exit_velo_last30":       avg_exit_velo_last30,
        "sweet_spot_pct_last30":      sweet_spot_pct_last30,
        "pa_per_game_last14":         pa_per_game_last14,
        "h_per_pa_vs_hand_last60":    h_per_pa_vs_hand_last60,
        "opp_k_pct":                  opp_k_pct,
        "opp_hard_hit_pct_allowed":   opp_hard_hit_pct_allowed,
        "opp_xba_allowed":            opp_xba_allowed,
        "park_factor":                park_factor,
        "is_home":                    is_home,
        "hits_in_game":               hits,
    })


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(use_real_data: bool = False, _override_df: pd.DataFrame = None):
    print("=== StrikeEdge Hitting Model Training ===\n")

    if _override_df is not None:
        df = _override_df
        print(f"Using provided dataset: {len(df):,} rows")
    else:
        data_path = Path("artifacts/hitting_train.parquet")
        if data_path.exists():
            print(f"Loading real dataset from {data_path}...")
            df = pd.read_parquet(data_path)
            print(f"Loaded {len(df):,} rows")
        else:
            print("No dataset found — generating calibrated synthetic data (12,000 batter-games)...")
            df = _generate_synthetic_data(n_rows=12_000)

    target_col = "hits_in_game"
    print(f"\nTarget — mean: {df[target_col].mean():.3f}, std: {df[target_col].std():.3f}")
    print(f"  0H: {(df[target_col]==0).mean():.1%}  "
          f"1H: {(df[target_col]==1).mean():.1%}  "
          f"2H+: {(df[target_col]>=2).mean():.1%}")

    X = df[HITTING_FEATURE_COLS].copy()
    y = df[target_col].values.astype(float)

    # count:poisson — correct objective for non-negative integer counts
    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", xgb.XGBRegressor(
            objective        = "count:poisson",
            n_estimators     = 800,
            max_depth        = 4,
            learning_rate    = 0.025,
            subsample        = 0.80,
            colsample_bytree = 0.70,
            min_child_weight = 8,
            reg_alpha        = 0.3,
            reg_lambda       = 2.5,
            random_state     = 42,
            n_jobs           = -1,
        )),
    ])

    print("\nCross-validating (5-fold KFold)...")
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    neg_mae = cross_val_score(pipeline, X, y, cv=cv, scoring="neg_mean_absolute_error")
    cv_mae  = -neg_mae.mean()
    cv_std  = neg_mae.std()
    print(f"  CV MAE:  {cv_mae:.4f} ± {cv_std:.4f} hits/game")

    print("\nFitting final model on full training set...")
    pipeline.fit(X, y)

    y_pred       = pipeline.predict(X)
    train_mae    = mean_absolute_error(y, y_pred)
    residual_std = float(np.std(y - y_pred))
    print(f"  Train MAE:    {train_mae:.4f} hits/game")
    print(f"  Residual std: {residual_std:.4f}  (used in P(hits > line) normal CDF)")

    # Linear calibration: fit predicted → actual on training set
    # Corrects systematic over/under-prediction bias
    lr = LinearRegression().fit(y_pred.reshape(-1, 1), y)
    cal_slope     = float(lr.coef_[0])
    cal_intercept = float(lr.intercept_)
    print(f"\nCalibration: slope={cal_slope:.4f}, intercept={cal_intercept:.4f}")

    xgb_model = pipeline.named_steps["model"]
    importances = dict(zip(HITTING_FEATURE_COLS, xgb_model.feature_importances_))
    top = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]
    print("\nTop feature importances:")
    for feat, imp in top:
        print(f"  {feat:<35} {imp:.4f}")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, ARTIFACT_PATH)
    print(f"\nModel saved: {ARTIFACT_PATH}")

    data_source = "synthetic_calibrated"
    if _override_df is not None or Path("artifacts/hitting_train.parquet").exists():
        data_source = "real_statcast"

    metrics = {
        "cv_mae":              round(float(cv_mae), 5),
        "cv_mae_std":          round(float(cv_std), 5),
        "train_mae":           round(float(train_mae), 5),
        "residual_std":        round(residual_std, 5),
        "calibration_slope":   round(cal_slope, 5),
        "calibration_intercept": round(cal_intercept, 5),
        "n_samples":           int(len(df)),
        "objective":           "count:poisson",
        "data_source":         data_source,
        "features":            HITTING_FEATURE_COLS,
        "top_features":        {k: round(float(v), 4) for k, v in top},
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"Metrics saved: {METRICS_PATH}")
    return metrics


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-data", action="store_true",
                        help="Force use of artifacts/hitting_train.parquet")
    args = parser.parse_args()
    train(use_real_data=args.real_data)

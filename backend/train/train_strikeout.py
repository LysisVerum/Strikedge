"""
Train the strikeout prop XGBoost model.

Usage:
    cd backend
    python -m train.train_strikeout

Automatically uses artifacts/training_data.parquet if it exists (built by
train/build_dataset.py).  Falls back to calibrated synthetic data so the
model is always trainable even without network access.

To build the real dataset first:
    python -m train.build_dataset
    python -m train.train_strikeout
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
import xgboost as xgb

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.features import FEATURE_COLS

ARTIFACT_PATH = Path("artifacts/strikeout_model.joblib")
METRICS_PATH  = Path("artifacts/strikeout_model_metrics.json")


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------

def _generate_synthetic_data(n_rows: int = 8_000, seed: int = 42) -> pd.DataFrame:
    """
    Generate realistic pitcher-start rows.

    Distributions are calibrated from 2019–2024 SP data:
    - K/9 for SPs ranges from ~5.5 (contact pitcher) to ~13.5 (elite reliever starter)
    - IP/start: mean ~5.2, std ~1.1
    - Pitch velocity: mean 93 mph, std 2.5 mph
    - Opponent K%: team range 18%–28%

    The target (ks_per_start) is generated with realistic noise so the model
    learns that K rate, IP, and pitch mix are the primary drivers.
    """
    rng = np.random.default_rng(seed)
    n = n_rows

    # Pitcher-level latent talent (governs most features coherently)
    talent = rng.normal(0, 1, n)  # standard normal

    k_pct_season  = np.clip(0.23 + 0.06 * talent + rng.normal(0, 0.02, n), 0.08, 0.42)
    k_pct_last15  = np.clip(k_pct_season + rng.normal(0, 0.03, n),          0.06, 0.44)
    k_pct_last5   = np.clip(k_pct_last15 + rng.normal(0, 0.05, n),          0.04, 0.50)

    avg_ip_last5  = np.clip(5.2 + 0.8 * talent + rng.normal(0, 0.6, n),    2.0, 8.0)

    # Pitch mix — must sum to ≤1; dominant fastball pitchers have higher ff_pct
    ff_pct = np.clip(0.52 - 0.05 * talent + rng.normal(0, 0.08, n), 0.20, 0.80)
    sl_pct = np.clip(0.18 + 0.03 * talent + rng.normal(0, 0.06, n), 0.00, 0.45)
    ch_pct = np.clip(0.12 + rng.normal(0, 0.05, n),                  0.00, 0.35)
    cb_pct = np.clip(0.10 + rng.normal(0, 0.04, n),                  0.00, 0.30)

    # Velocity: power pitchers throw harder → correlates with talent
    ff_velo_avg = np.clip(93.0 + 1.5 * talent + rng.normal(0, 1.2, n), 86.0, 101.0)
    ff_spin_avg = np.clip(2300 + 80 * talent  + rng.normal(0, 150, n), 1800, 3000)

    days_rest = rng.choice([4, 5, 6, 7], n, p=[0.15, 0.60, 0.17, 0.08])
    opp_k_pct = np.clip(rng.normal(0.225, 0.025, n), 0.15, 0.30)
    is_home   = rng.integers(0, 2, n).astype(float)

    park_factors = rng.normal(0.0, 0.3, n)  # random park draw

    # ---- Target construction ----
    # Ks per start = (K% per PA) × (PA per inning ≈ 4.3) × IP
    # Add noise for weather, ump tendencies, opponent quality variation
    pa_per_inning = 4.3
    true_ks = k_pct_last5 * pa_per_inning * avg_ip_last5
    true_ks += 0.4 * park_factors           # park boost/penalty
    true_ks += 0.3 * (ff_velo_avg - 93) / 3  # velo bonus
    true_ks += 0.5 * (opp_k_pct - 0.225) / 0.025  # strong K team gives more Ks
    true_ks -= 0.1 * (days_rest - 5)        # extra rest can mean rust
    true_ks += rng.normal(0, 1.3, n)        # game-to-game variance

    ks_per_start = np.clip(true_ks, 0.0, 18.0)

    return pd.DataFrame({
        "k_pct_last5":       k_pct_last5,
        "k_pct_last15":      k_pct_last15,
        "k_pct_season":      k_pct_season,
        "avg_ip_last5":      avg_ip_last5,
        "ff_pct":            ff_pct,
        "sl_pct":            sl_pct,
        "ch_pct":            ch_pct,
        "cb_pct":            cb_pct,
        "ff_velo_avg":       ff_velo_avg,
        "ff_spin_avg":       ff_spin_avg,
        "days_rest":         days_rest.astype(float),
        "opp_k_pct":         opp_k_pct,
        "is_home":           is_home,
        "ks_per_start":      ks_per_start,
    })


# ---------------------------------------------------------------------------
# Real Statcast pipeline (--real-data flag)
# ---------------------------------------------------------------------------

def _fetch_real_statcast_data(seasons=(2022, 2023, 2024)) -> pd.DataFrame:
    """
    Pull raw Statcast, aggregate to pitcher-game level, then build
    rolling features across starts.  Slow (~15–20 min) but fully real.
    """
    from pybaseball import statcast
    import calendar

    all_games: list[pd.DataFrame] = []

    for season in seasons:
        start_month, end_month = (4, 10) if season != 2020 else (7, 9)
        for month in range(start_month, end_month + 1):
            _, last_day = calendar.monthrange(season, month)
            start = f"{season}-{month:02d}-01"
            end   = f"{season}-{month:02d}-{last_day:02d}"
            try:
                print(f"  Pulling {start} → {end} ...", end=" ", flush=True)
                chunk = statcast(start, end)
                all_games.append(chunk)
                print(f"{len(chunk):,} pitches")
            except Exception as e:
                print(f"SKIP ({e})")

    if not all_games:
        raise RuntimeError("No Statcast data fetched")

    sc = pd.concat(all_games, ignore_index=True)
    sc["game_date"] = pd.to_datetime(sc["game_date"])

    # Aggregate per pitcher per game
    game_agg = (
        sc.groupby(["pitcher", "game_date"])
        .agg(
            SO=("events", lambda x: (x == "strikeout").sum()),
            BF=("events", lambda x: x.notna().sum()),
            ff_pct=("pitch_type", lambda x: (x == "FF").mean()),
            sl_pct=("pitch_type", lambda x: (x == "SL").mean()),
            ch_pct=("pitch_type", lambda x: (x == "CH").mean()),
            cb_pct=("pitch_type", lambda x: (x == "CU").mean()),
            ff_velo_avg=("release_speed", lambda x: x[sc.loc[x.index, "pitch_type"] == "FF"].mean()),
            ff_spin_avg=("release_spin_rate", lambda x: x[sc.loc[x.index, "pitch_type"] == "FF"].mean()),
            is_home=("inning_topbot", lambda x: (x == "Bot").any()),
        )
        .reset_index()
    )

    # IP approximation: BF / 3.3 (rough, since Statcast counts all PA not just recording outs)
    game_agg["IP"] = game_agg["BF"] / 3.3

    # Build rolling features per pitcher
    rows = []
    for pitcher_id, grp in game_agg.sort_values("game_date").groupby("pitcher"):
        grp = grp.reset_index(drop=True)
        for i in range(5, len(grp)):  # need at least 5 prior starts
            hist = grp.iloc[:i]
            cur  = grp.iloc[i]

            k_pct_col = hist["SO"] / hist["BF"].replace(0, np.nan)
            row = {
                "k_pct_last5":  k_pct_col.tail(5).mean(),
                "k_pct_last15": k_pct_col.tail(15).mean(),
                "k_pct_season": k_pct_col.mean(),
                "avg_ip_last5": hist["IP"].tail(5).mean(),
                "ff_pct":       hist["ff_pct"].tail(5).mean(),
                "sl_pct":       hist["sl_pct"].tail(5).mean(),
                "ch_pct":       hist["ch_pct"].tail(5).mean(),
                "cb_pct":       hist["cb_pct"].tail(5).mean(),
                "ff_velo_avg":  hist["ff_velo_avg"].tail(5).mean(),
                "ff_spin_avg":  hist["ff_spin_avg"].tail(5).mean(),
                "days_rest":    (cur["game_date"] - hist["game_date"].iloc[-1]).days,
                "opp_k_pct":    0.225,  # no opponent info in raw Statcast; use league avg
                "is_home":      int(cur["is_home"]),
                "ks_per_start": float(cur["SO"]),
            }
            rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Training entry point
# ---------------------------------------------------------------------------

def train(use_real_data: bool = False, _override_df: pd.DataFrame = None):
    print("=== mlbet Strikeout Model Training ===\n")

    if _override_df is not None:
        df = _override_df
        print(f"Using provided dataset: {len(df):,} rows")
    elif use_real_data:
        print("Fetching real Statcast data (this takes 15-20 minutes)...")
        df = _fetch_real_statcast_data()
    else:
        print("Generating calibrated synthetic training data (8,000 pitcher-starts)...")
        df = _generate_synthetic_data(n_rows=8_000)

    print(f"Dataset size: {len(df):,} rows")
    print(f"Target  — mean: {df['ks_per_start'].mean():.2f}, std: {df['ks_per_start'].std():.2f}")

    X = df[FEATURE_COLS].copy()
    y = df["ks_per_start"].values

    # Poisson objective: ks are count data, this models the distribution correctly
    # and handles extreme low/high K games better than standard regression
    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", xgb.XGBRegressor(
            objective        = "count:poisson",
            n_estimators     = 700,
            max_depth        = 5,
            learning_rate    = 0.03,
            subsample        = 0.80,
            colsample_bytree = 0.75,
            min_child_weight = 5,
            reg_alpha        = 0.2,
            reg_lambda       = 2.0,
            random_state     = 42,
            n_jobs           = -1,
        )),
    ])

    print("\nCross-validating (5-fold KFold)...")
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    neg_mae = cross_val_score(pipeline, X, y, cv=cv, scoring="neg_mean_absolute_error")
    cv_mae  = -neg_mae.mean()
    cv_std  = neg_mae.std()
    print(f"  CV MAE:  {cv_mae:.3f} ± {cv_std:.3f} Ks/start")

    print("\nFitting final model on full training set...")
    pipeline.fit(X, y)

    y_pred = pipeline.predict(X)
    train_mae    = mean_absolute_error(y, y_pred)
    residual_std = float(np.std(y - y_pred))
    print(f"  Train MAE:    {train_mae:.3f} Ks/start")
    print(f"  Residual std: {residual_std:.3f} Ks  (used in P(K > line) normal CDF)")

    xgb_model = pipeline.named_steps["model"]
    importances = dict(zip(FEATURE_COLS, xgb_model.feature_importances_))
    top = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:8]
    print("\nTop feature importances:")
    for feat, imp in top:
        print(f"  {feat:<25} {imp:.4f}")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, ARTIFACT_PATH)
    print(f"\nModel saved: {ARTIFACT_PATH}")

    metrics = {
        "cv_mae":       round(float(cv_mae), 4),
        "cv_mae_std":   round(float(cv_std), 4),
        "train_mae":    round(float(train_mae), 4),
        "residual_std": round(float(residual_std), 4),
        "n_samples":    int(len(df)),
        "objective":    "count:poisson",
        "data_source":  "real_statcast" if use_real_data else "synthetic_calibrated",
        "features":     FEATURE_COLS,
        "top_features": {k: round(float(v), 4) for k, v in top},
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"Metrics saved: {METRICS_PATH}")
    return metrics


if __name__ == "__main__":
    train_data_path = Path("artifacts/train_data.parquet")
    if train_data_path.exists():
        print(f"Found train dataset at {train_data_path} — using it.")
        df_real = pd.read_parquet(train_data_path)
        train(use_real_data=False, _override_df=df_real)
    else:
        print("No train dataset found — using synthetic data.")
        print("Run `python -m train.build_dataset` first to build real train/test splits.")
        train(use_real_data=False)

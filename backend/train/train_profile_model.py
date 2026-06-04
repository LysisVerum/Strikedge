"""
Train the profile-based strikeout model.

Uses PROFILE_FEATURE_COLS from features.py — stable career talent +
pitch quality + matchup scoring instead of noisy rolling windows.

Usage:
    cd backend
    python -m train.train_profile_model
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

from app.models.features import PROFILE_FEATURE_COLS

ARTIFACT_PATH = Path("artifacts/profile_model.joblib")
METRICS_PATH  = Path("artifacts/profile_model_metrics.json")
TRAIN_PATH    = Path("artifacts/profile_train.parquet")
TEST_PATH     = Path("artifacts/profile_test_2025.parquet")

RECENCY_WEIGHTS = {
    2016: 1.0, 2017: 1.0, 2018: 1.2, 2019: 1.2,
    2021: 1.5, 2022: 2.0, 2023: 2.5, 2024: 3.0,
}


def train():
    print("=== Profile-Based Strikeout Model ===\n")

    if not TRAIN_PATH.exists():
        print(f"No training data at {TRAIN_PATH}.")
        print("Run: python -m train.build_profile_dataset")
        return

    df_train = pd.read_parquet(TRAIN_PATH)
    print(f"Train: {len(df_train):,} rows  seasons {sorted(df_train['season'].unique().tolist())}")

    if TEST_PATH.exists():
        df_test = pd.read_parquet(TEST_PATH)
        test_seasons = sorted(df_test['season'].unique().tolist())
        # Sanity: no overlap
        overlap = set(df_train['season'].unique()) & set(df_test['season'].unique())
        if overlap:
            print(f"ERROR: train/test overlap on seasons {overlap}")
            return
        print(f"Test:  {len(df_test):,} rows  seasons {test_seasons}")
    else:
        df_test = None
        print("No test parquet found — skipping hold-out evaluation.")

    print(f"\nTarget — mean: {df_train['ks_per_start'].mean():.2f}  std: {df_train['ks_per_start'].std():.2f}")

    X_train = df_train[PROFILE_FEATURE_COLS]
    y_train = df_train["ks_per_start"].values
    sw      = df_train["season"].map(RECENCY_WEIGHTS).fillna(1.0).values

    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model",   xgb.XGBRegressor(
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

    print("\nCross-validating (5-fold)...")
    cv     = KFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(pipeline, X_train, y_train, cv=cv,
                             scoring="neg_mean_absolute_error")
    cv_mae = -scores.mean()
    cv_std = scores.std()
    print(f"  CV MAE: {cv_mae:.3f} ± {cv_std:.3f} Ks/start")

    print("\nFitting on full training set...")
    pipeline.fit(X_train, y_train, model__sample_weight=sw)
    train_mae = mean_absolute_error(y_train, pipeline.predict(X_train))
    print(f"  Train MAE: {train_mae:.3f}")

    # Hold-out evaluation + calibration
    test_mae = residual_std = cal_slope = cal_intercept = None
    if df_test is not None:
        X_test  = df_test[PROFILE_FEATURE_COLS]
        y_test  = df_test["ks_per_start"].values
        pred    = pipeline.predict(X_test)
        test_mae     = float(mean_absolute_error(y_test, pred))
        residual_std = float(np.std(y_test - pred))
        bias         = float(np.mean(pred - y_test))
        coeffs       = np.polyfit(pred, y_test, 1)
        cal_slope    = float(coeffs[0])
        cal_intercept= float(coeffs[1])
        print(f"  Test MAE (2025): {test_mae:.3f}  bias={bias:+.3f}  std={residual_std:.3f}")
        print(f"  Calibration:     slope={cal_slope:.4f}  intercept={cal_intercept:.4f}")

    # Feature importances
    model = pipeline.named_steps["model"]
    imps  = dict(zip(PROFILE_FEATURE_COLS, model.feature_importances_))
    top   = sorted(imps.items(), key=lambda x: x[1], reverse=True)
    print("\nFeature importances:")
    for feat, imp in top:
        print(f"  {feat:<28} {imp:.4f}")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, ARTIFACT_PATH)
    print(f"\nModel saved: {ARTIFACT_PATH}")

    metrics = {
        "cv_mae":               round(cv_mae, 4),
        "cv_mae_std":           round(cv_std, 4),
        "train_mae":            round(train_mae, 4),
        "test_mae":             round(test_mae, 4)        if test_mae        else None,
        "residual_std":         round(residual_std, 4)    if residual_std    else None,
        "calibration_slope":    round(cal_slope, 4)       if cal_slope       else None,
        "calibration_intercept":round(cal_intercept, 4)   if cal_intercept   else None,
        "n_samples":            int(len(df_train)),
        "objective":            "count:poisson",
        "data_source":          "profile_based",
        "features":             PROFILE_FEATURE_COLS,
        "train_seasons":        sorted(df_train["season"].unique().tolist()),
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"Metrics saved: {METRICS_PATH}")
    return metrics


if __name__ == "__main__":
    train()

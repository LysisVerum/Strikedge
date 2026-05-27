"""
Train an experimental Random Forest model for strikeout prediction.

Saves to artifacts/strikeout_model_rf.joblib so it doesn't overwrite
the production XGBoost model. Run compare_models.py afterwards to see
which model wins on the held-out test set.

Usage:
    cd backend
    python -m train.train_strikeout_rf
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score, KFold, RandomizedSearchCV
from sklearn.metrics import mean_absolute_error
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.features import FEATURE_COLS

ARTIFACT_PATH = Path("artifacts/strikeout_model_rf.joblib")
METRICS_PATH  = Path("artifacts/strikeout_model_rf_metrics.json")


def train():
    print("=== Experimental Random Forest Model ===\n")

    train_path = Path("artifacts/train_data.parquet")
    if not train_path.exists():
        print("ERROR: artifacts/train_data.parquet not found.")
        print("Run: python -m train.build_dataset first.")
        sys.exit(1)

    df = pd.read_parquet(train_path)
    print(f"Training data: {len(df):,} rows ({df['season'].min():.0f}-{df['season'].max():.0f})")
    print(f"Target — mean: {df['ks_per_start'].mean():.2f}, std: {df['ks_per_start'].std():.2f}\n")

    X = df[FEATURE_COLS].copy()
    y = df["ks_per_start"].values

    # Recency weights (same as XGBoost trainer for a fair comparison)
    _year_weights = {2016: 1.0, 2017: 1.0, 2018: 1.2, 2019: 1.2,
                     2021: 1.5, 2022: 2.0, 2023: 2.5, 2024: 3.0, 2025: 3.0}
    sample_weight = df["season"].map(_year_weights).fillna(1.0).values if "season" in df.columns else None

    # ---- Hyperparameter search ----
    # RandomizedSearchCV with 3-fold CV to find a good RF config quickly (~2-3 min)
    print("Searching hyperparameters (RandomizedSearchCV, 3-fold, 30 iterations)...")
    param_dist = {
        "model__n_estimators":      [300, 500, 700, 1000],
        "model__max_depth":         [None, 15, 20, 25],
        "model__min_samples_split": [2, 5, 10],
        "model__min_samples_leaf":  [1, 2, 3, 5],
        "model__max_features":      ["sqrt", "log2", 0.5, 0.7],
        "model__max_samples":       [0.7, 0.8, 0.9, None],
    }

    base_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", RandomForestRegressor(random_state=42, n_jobs=-1)),
    ])

    search = RandomizedSearchCV(
        base_pipe,
        param_distributions=param_dist,
        n_iter=30,
        cv=3,
        scoring="neg_mean_absolute_error",
        random_state=42,
        n_jobs=1,   # outer loop: 1 job; RF itself uses n_jobs=-1 internally
        verbose=1,
    )
    search.fit(X, y)
    best_params = search.best_params_
    search_mae = -search.best_score_

    print(f"\nBest search MAE (3-fold): {search_mae:.3f}")
    print("Best params:")
    for k, v in best_params.items():
        print(f"  {k.replace('model__', '')}: {v}")

    # ---- 5-fold CV with best params (for fair comparison with XGBoost metrics) ----
    print("\nCross-validating best config (5-fold KFold)...")
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    neg_mae = cross_val_score(search.best_estimator_, X, y, cv=cv, scoring="neg_mean_absolute_error")
    cv_mae = -neg_mae.mean()
    cv_std =  neg_mae.std()
    print(f"  CV MAE:  {cv_mae:.3f} ± {cv_std:.3f} Ks/start")

    # ---- Final fit on full training set ----
    print("\nFitting final model on full training set...")
    pipeline = search.best_estimator_
    if sample_weight is not None:
        pipeline.fit(X, y, model__sample_weight=sample_weight)
    else:
        pipeline.fit(X, y)

    y_pred = pipeline.predict(X)
    train_mae    = mean_absolute_error(y, y_pred)
    residual_std = float(np.std(y - y_pred))
    print(f"  Train MAE:    {train_mae:.3f} Ks/start")
    print(f"  Residual std: {residual_std:.3f} Ks")

    rf_model = pipeline.named_steps["model"]
    importances = dict(zip(FEATURE_COLS, rf_model.feature_importances_))
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
        "model_type":   "random_forest",
        "best_params":  {k.replace("model__", ""): str(v) for k, v in best_params.items()},
        "features":     FEATURE_COLS,
        "top_features": {k: round(float(v), 4) for k, v in top},
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"Metrics saved: {METRICS_PATH}")
    return metrics


if __name__ == "__main__":
    train()

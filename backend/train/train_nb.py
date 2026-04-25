"""
Negative Binomial regression model — comparison against XGBoost Poisson.

Usage:
    cd backend
    python -m train.train_nb

Loads train_data.parquet and test_data.parquet (built by train/build_dataset.py),
fits statsmodels NegativeBinomial on the training set, evaluates both models on
the held-out test set, prints a side-by-side comparison table, and saves the
better-performing model as the default strikeout_model.joblib.
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.features import FEATURE_COLS

ARTIFACTS       = Path("artifacts")
XGB_PATH        = ARTIFACTS / "strikeout_model.joblib"
NB_PATH         = ARTIFACTS / "nb_model.joblib"
METRICS_PATH    = ARTIFACTS / "strikeout_model_metrics.json"
NB_METRICS_PATH = ARTIFACTS / "nb_model_metrics.json"
TRAIN_PATH      = ARTIFACTS / "train_data.parquet"
TEST_PATH       = ARTIFACTS / "test_data.parquet"


# ---------------------------------------------------------------------------
# NBWrapper — sklearn-compatible interface around statsmodels NegBin
# ---------------------------------------------------------------------------

class NBWrapper:
    """
    Wraps statsmodels NegativeBinomial so it has a sklearn-compatible
    .predict(X) interface.  Handles imputation and scaling internally.
    """

    def __init__(self, result, imputer: SimpleImputer, scaler=None):
        self._result  = result
        self._imputer = imputer
        self._scaler  = scaler

    def predict(self, X) -> np.ndarray:
        import statsmodels.api as sm
        if hasattr(X, "values"):
            X = X.values
        X_imp = self._imputer.transform(X)
        if self._scaler is not None:
            X_imp = self._scaler.transform(X_imp)
        X_const = sm.add_constant(X_imp, has_constant="add")
        return self._result.predict(X_const)


# ---------------------------------------------------------------------------
# Bias-by-bucket helper
# ---------------------------------------------------------------------------

BUCKETS = [(3, 5), (5, 7), (7, 9), (9, 15)]

def _bucket_label(lo: float, hi: float) -> str:
    return f"{lo}-{hi}K"

def bias_by_bucket(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Return mean (pred - actual) per predicted K-count bucket."""
    results = {}
    for lo, hi in BUCKETS:
        mask = (y_pred >= lo) & (y_pred < hi)
        if mask.sum() == 0:
            results[_bucket_label(lo, hi)] = float("nan")
        else:
            bias = float(np.mean(y_pred[mask] - y_true[mask]))
            results[_bucket_label(lo, hi)] = round(bias, 3)
    return results


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_nb(X_train: np.ndarray, y_train: np.ndarray, imputer: SimpleImputer):
    import statsmodels.api as sm
    from sklearn.preprocessing import StandardScaler

    X_imp = imputer.transform(X_train)

    # Scale features so MLE optimizer isn't fighting wildly different magnitudes
    scaler  = StandardScaler()
    X_scaled = scaler.fit_transform(X_imp)
    X_const  = sm.add_constant(X_scaled, has_constant="add")

    model = sm.NegativeBinomial(y_train, X_const)

    # Provide start_params to skip the internal Newton-based Poisson warm-start
    # which fails on correlated features (singular Hessian).
    # intercept = log(mean(y)), all betas = 0, alpha (dispersion) = 1.
    n_params    = X_const.shape[1]
    start_p     = np.zeros(n_params + 1)
    start_p[0]  = np.log(np.mean(y_train) + 1e-6)
    start_p[-1] = 1.0  # alpha (dispersion)

    print("Fitting Negative Binomial regression (BFGS)...")
    result = model.fit(start_params=start_p, maxiter=500, disp=False,
                       method="bfgs", warn_convergence=False)
    print(f"  NB converged: {result.mle_retvals['converged']}")
    print(f"  Log-likelihood: {result.llf:.1f}")

    return NBWrapper(result, imputer, scaler)


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def run():
    if not TRAIN_PATH.exists() or not TEST_PATH.exists():
        print("ERROR: train_data.parquet / test_data.parquet not found.")
        print("Run `python -m train.build_dataset` first.")
        sys.exit(1)

    print("=== Negative Binomial vs XGBoost Poisson Comparison ===\n")

    train_df = pd.read_parquet(TRAIN_PATH)
    test_df  = pd.read_parquet(TEST_PATH)

    print(f"Train: {len(train_df):,} rows   Test: {len(test_df):,} rows")

    X_train = train_df[FEATURE_COLS].values
    y_train = train_df["ks_per_start"].values.astype(float)
    X_test  = test_df[FEATURE_COLS].values
    y_test  = test_df["ks_per_start"].values.astype(float)

    # Shared imputer (median) — same strategy as XGBoost pipeline
    imputer = SimpleImputer(strategy="median")
    imputer.fit(X_train)

    # ---- Negative Binomial ----
    nb_wrapper = train_nb(X_train, y_train, imputer)
    nb_pred    = nb_wrapper.predict(X_test)
    nb_mae     = float(mean_absolute_error(y_test, nb_pred))
    nb_bias    = float(np.mean(nb_pred - y_test))
    nb_buckets = bias_by_bucket(y_test, nb_pred)

    # Save NB model and metrics regardless of winner
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    joblib.dump(nb_wrapper, NB_PATH)
    nb_metrics = {
        "model_type":   "negative_binomial",
        "test_mae":     round(nb_mae, 4),
        "test_bias":    round(nb_bias, 4),
        "bias_buckets": nb_buckets,
        "n_test":       int(len(y_test)),
    }
    NB_METRICS_PATH.write_text(json.dumps(nb_metrics, indent=2))

    # ---- XGBoost (existing model) ----
    if not XGB_PATH.exists():
        print("\nWARNING: strikeout_model.joblib not found — run train_strikeout.py first.")
        xgb_mae     = float("inf")
        xgb_bias    = float("nan")
        xgb_buckets = {_bucket_label(lo, hi): float("nan") for lo, hi in BUCKETS}
    else:
        xgb_pipeline = joblib.load(XGB_PATH)
        xgb_pred     = xgb_pipeline.predict(test_df[FEATURE_COLS])
        xgb_mae      = float(mean_absolute_error(y_test, xgb_pred))
        xgb_bias     = float(np.mean(xgb_pred - y_test))
        xgb_buckets  = bias_by_bucket(y_test, xgb_pred)

    # ---- Side-by-side table ----
    print("\n" + "=" * 60)
    print(f"{'Metric':<28} {'XGBoost Poisson':>15} {'Neg Binomial':>14}")
    print("-" * 60)
    print(f"{'Test MAE':<28} {xgb_mae:>15.4f} {nb_mae:>14.4f}")
    print(f"{'Avg bias (pred-actual)':<28} {xgb_bias:>15.4f} {nb_bias:>14.4f}")
    print("-" * 60)
    print("Avg bias by predicted K bucket:")
    for lo, hi in BUCKETS:
        label = _bucket_label(lo, hi)
        xb    = xgb_buckets.get(label, float("nan"))
        nb    = nb_buckets.get(label, float("nan"))
        xb_s  = f"{xb:+.3f}" if not np.isnan(xb) else "  n/a"
        nb_s  = f"{nb:+.3f}" if not np.isnan(nb) else "  n/a"
        print(f"  {label:<26} {xb_s:>15} {nb_s:>14}")
    print("=" * 60)

    # ---- Decide default ----
    nb_wins = nb_mae < xgb_mae
    print(f"\nVerdict: {'NB wins' if nb_wins else 'XGBoost wins'} "
          f"(MAE delta = {abs(xgb_mae - nb_mae):.4f} Ks)")

    if nb_wins:
        print("\nNB has lower test MAE — promoting to default model.")
        # Back up XGBoost first
        xgb_backup = ARTIFACTS / "xgb_model.joblib"
        if XGB_PATH.exists():
            XGB_PATH.rename(xgb_backup)
            print(f"  XGBoost backed up -> {xgb_backup}")

        # Write NB wrapper as the new default
        joblib.dump(nb_wrapper, XGB_PATH)
        print(f"  NB model saved as {XGB_PATH}")

        # Update metrics file so strikeout.py picks up correct residual_std
        existing = {}
        if METRICS_PATH.exists():
            try:
                existing = json.loads(METRICS_PATH.read_text())
            except Exception:
                pass

        # Compute residual std on test set for the NB predictions
        residual_std = float(np.std(nb_pred - y_test))
        existing.update({
            "model_type":        "negative_binomial",
            "test_mae":          round(nb_mae, 4),
            "residual_std":      round(residual_std, 4),
            "calibration_slope": 1.0,      # NB predictions are already unbiased
            "calibration_intercept": 0.0,
        })
        METRICS_PATH.write_text(json.dumps(existing, indent=2))
        print(f"  Metrics updated: {METRICS_PATH}")
    else:
        print("\nXGBoost remains default.  NB model saved to nb_model.joblib for reference.")
        # Ensure calibration stays meaningful — re-derive residual_std from XGBoost predictions
        if XGB_PATH.exists():
            xgb_pipeline = joblib.load(XGB_PATH)
            xgb_pred_train = xgb_pipeline.predict(train_df[FEATURE_COLS])
            residual_std   = float(np.std(y_train - xgb_pred_train))
            existing = {}
            if METRICS_PATH.exists():
                try:
                    existing = json.loads(METRICS_PATH.read_text())
                except Exception:
                    pass
            existing["residual_std"] = round(residual_std, 4)
            METRICS_PATH.write_text(json.dumps(existing, indent=2))


if __name__ == "__main__":
    run()

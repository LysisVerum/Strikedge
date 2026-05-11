"""
Hitting prop prediction model wrapper.

Loads a trained XGBoost regressor and exposes a predict() method that
returns the model's expected hit total plus a confidence interval.
Edge is computed by comparing model probability to an asymmetric threshold:
  OVER:  model_prob_over - implied_prob_over >= 0.15
  UNDER: model_prob_under - implied_prob_under >= 0.10
"""
import os
import json
import warnings
import pandas as pd
import joblib
from pathlib import Path
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Feature columns
# ---------------------------------------------------------------------------

HITTING_FEATURE_COLS = [
    # Rolling H/PA (recent form)
    "h_per_pa_last7",
    "h_per_pa_last14",
    "h_per_pa_last30",
    "h_per_pa_season",
    # Statcast contact quality (rolling 30-day)
    "barrel_rate_last30",
    "hard_hit_pct_last30",
    "xba_last30",
    "avg_exit_velo_last30",
    "sweet_spot_pct_last30",
    # Expected PAs this game (lineup spot proxy)
    "pa_per_game_last14",
    # Platoon: H/PA vs today's pitcher handedness (last 60 days)
    "h_per_pa_vs_hand_last60",
    # Opponent pitcher quality (rolling prior 5 starts)
    "opp_k_pct",
    "opp_hard_hit_pct_allowed",
    "opp_xba_allowed",
    # Context
    "park_factor",
    "is_home",
]

# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------

_default_path = Path(__file__).parent.parent.parent / "artifacts" / "hitting_model.joblib"
_metrics_path = Path(__file__).parent.parent.parent / "artifacts" / "hitting_model_metrics.json"
MODEL_PATH = Path(os.getenv("HITTING_MODEL_ARTIFACT_PATH", str(_default_path)))

_FALLBACK_CAL_SLOPE      = 0.92
_FALLBACK_CAL_INTERCEPT  = 0.08


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def _load_metrics() -> dict:
    try:
        if _metrics_path.exists():
            return json.loads(_metrics_path.read_text())
    except Exception:
        pass
    return {}


def _calibrate(raw: float) -> float:
    """Apply linear calibration to correct systematic bias."""
    m = _load_metrics()
    slope     = float(m.get("calibration_slope",     _FALLBACK_CAL_SLOPE))
    intercept = float(m.get("calibration_intercept", _FALLBACK_CAL_INTERCEPT))
    return slope * raw + intercept


# ---------------------------------------------------------------------------
# Prediction dataclass
# ---------------------------------------------------------------------------

@dataclass
class HittingPrediction:
    batter_name: str
    matchup: str             # "NYY vs BOS"
    predicted_hits: float
    line: float              # sportsbook O/U line (e.g. 0.5, 1.5, 2.5)
    model_prob_over: float   # model's probability of going over the line
    implied_prob_over: float # book's implied prob from the over price
    edge_pct: float          # model_prob - implied_prob (positive = bet over)
    confidence: str          # "HIGH" / "MEDIUM" / "LOW"
    recommendation: str      # "OVER" / "UNDER" / "PASS"
    features_used: dict


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _confidence_tier(edge_pct: float) -> str:
    if abs(edge_pct) >= 0.15:
        return "HIGH"
    if abs(edge_pct) >= 0.10:
        return "MEDIUM"
    return "LOW"


def _american_to_implied(odds: int) -> float:
    """Convert American moneyline odds to implied probability."""
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def _poisson_prob_over(predicted: float, line: float) -> float:
    """P(hits > line) using Poisson CDF — correct for small integer counts.

    DK lines are always half-integers (0.5, 1.5, 2.5), so floor(line) gives
    the last integer that counts as UNDER: P(over) = 1 - P(X <= floor(line)).
    """
    from scipy import stats
    mu = max(predicted, 0.01)   # guard against zero/negative predictions
    return float(1 - stats.poisson.cdf(int(line), mu=mu))


# ---------------------------------------------------------------------------
# Model class
# ---------------------------------------------------------------------------

class HittingModel:
    def __init__(self):
        self._model = None

    def load(self):
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model artifact not found at {MODEL_PATH}. "
                "Run train/train_hitting.py first."
            )
        self._model = joblib.load(MODEL_PATH)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def predict(
        self,
        feature_row: pd.Series,
        line: float,
        over_odds: int = -115,
        under_odds: int = -115,
        batter_name: str = "Unknown",
        matchup: str = "",
    ) -> HittingPrediction:
        if not self.is_loaded:
            self.load()

        X = feature_row[HITTING_FEATURE_COLS].values.reshape(1, -1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw_pred = float(self._model.predict(X)[0])

        predicted_hits   = max(0.0, _calibrate(raw_pred))
        model_prob_over  = _poisson_prob_over(predicted_hits, line)
        model_prob_under = 1 - model_prob_over

        edge_over  = model_prob_over  - _american_to_implied(over_odds)
        edge_under = model_prob_under - _american_to_implied(under_odds)

        if edge_over >= edge_under:
            edge_pct          = round(edge_over, 4)
            implied_prob_over = _american_to_implied(over_odds)
        else:
            edge_pct          = round(-edge_under, 4)   # negative = under is the better bet
            implied_prob_over = _american_to_implied(over_odds)

        confidence = _confidence_tier(edge_pct)

        # Asymmetric thresholds: OVER requires 15% edge, UNDER requires 10%
        if edge_over >= edge_under:
            recommendation = "OVER" if edge_over >= 0.15 else "PASS"
        elif edge_under >= 0.10:
            recommendation = "UNDER"
        else:
            recommendation = "PASS"

        return HittingPrediction(
            batter_name=batter_name,
            matchup=matchup,
            predicted_hits=round(predicted_hits, 2),
            line=line,
            model_prob_over=round(model_prob_over, 4),
            implied_prob_over=round(implied_prob_over, 4),
            edge_pct=edge_pct,
            confidence=confidence,
            recommendation=recommendation,
            features_used=feature_row.to_dict(),
        )


# Module-level singleton — loaded once at app startup
hitting_model = HittingModel()

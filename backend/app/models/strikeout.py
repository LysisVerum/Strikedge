"""
Strikeout prop prediction model wrapper.

Loads a trained XGBoost regressor and exposes a predict() method that
returns the model's expected K total plus a confidence interval.
The edge is computed by comparing model probability to the implied
probability derived from the sportsbook line.
"""
import os
import json
import warnings
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from dataclasses import dataclass
from app.models.features import FEATURE_COLS

_default_path = Path(__file__).parent.parent.parent / "artifacts" / "strikeout_model.joblib"
_metrics_path = Path(__file__).parent.parent.parent / "artifacts" / "strikeout_model_metrics.json"
MODEL_PATH = Path(os.getenv("MODEL_ARTIFACT_PATH", str(_default_path)))

_FALLBACK_RESIDUAL_STD   = 1.923
_FALLBACK_CAL_SLOPE      = 0.8947
_FALLBACK_CAL_INTERCEPT  = 0.4056

def _load_metrics() -> dict:
    try:
        if _metrics_path.exists():
            return json.loads(_metrics_path.read_text())
    except Exception:
        pass
    return {}

def _load_residual_std() -> float:
    return float(_load_metrics().get("residual_std", _FALLBACK_RESIDUAL_STD))

def _calibrate(raw: float) -> float:
    """Apply linear calibration to correct systematic overprediction bias."""
    m = _load_metrics()
    slope     = float(m.get("calibration_slope",     _FALLBACK_CAL_SLOPE))
    intercept = float(m.get("calibration_intercept", _FALLBACK_CAL_INTERCEPT))
    return slope * raw + intercept


@dataclass
class StrikeoutPrediction:
    pitcher_name: str
    matchup: str           # "NYY vs BOS"
    predicted_ks: float
    line: float            # sportsbook O/U line
    model_prob_over: float # model's probability of going over the line
    implied_prob_over: float  # book's implied prob from the line price
    edge_pct: float        # model_prob - implied_prob (positive = bet over)
    confidence: str        # "HIGH" / "MEDIUM" / "LOW"
    recommendation: str    # "OVER" / "UNDER" / "PASS"
    features_used: dict


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


def _normal_prob_over(predicted: float, line: float, std: float) -> float:
    from scipy import stats
    return float(1 - stats.norm.cdf(line + 0.5, loc=predicted, scale=std))


class StrikeoutModel:
    def __init__(self):
        self._model = None

    def load(self):
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model artifact not found at {MODEL_PATH}. "
                "Run train/train_strikeout.py first."
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
        pitcher_name: str = "Unknown",
        matchup: str = "",
    ) -> StrikeoutPrediction:
        if not self.is_loaded:
            self.load()

        X = feature_row[FEATURE_COLS].values.reshape(1, -1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            predicted_ks = float(self._model.predict(X)[0])

        std = _load_residual_std()
        model_prob_over  = _normal_prob_over(predicted_ks, line, std)
        model_prob_under = 1 - model_prob_over

        # Compute edge on both sides independently — pick whichever is better
        edge_over  = model_prob_over  - _american_to_implied(over_odds)
        edge_under = model_prob_under - _american_to_implied(under_odds)

        if edge_over >= edge_under:
            edge_pct = round(edge_over, 4)
            implied_prob_over = _american_to_implied(over_odds)
        else:
            edge_pct = round(-edge_under, 4)  # negative = under is the better bet
            implied_prob_over = _american_to_implied(over_odds)

        confidence = _confidence_tier(edge_pct)

        # OVER threshold scales with predicted Ks — model overpredicts more
        # at higher K totals, so we demand a larger edge to compensate.
        if predicted_ks < 4:
            over_threshold = 0.08
        elif predicted_ks < 6.5:
            over_threshold = 0.10
        else:
            over_threshold = 0.12

        if edge_over >= edge_under:
            recommendation = "OVER" if edge_over >= over_threshold else "PASS"
        elif edge_under >= 0.10:
            recommendation = "UNDER"
        else:
            recommendation = "PASS"

        return StrikeoutPrediction(
            pitcher_name=pitcher_name,
            matchup=matchup,
            predicted_ks=round(predicted_ks, 2),
            line=line,
            model_prob_over=round(model_prob_over, 4),
            implied_prob_over=round(implied_prob_over, 4),
            edge_pct=edge_pct,
            confidence=confidence,
            recommendation=recommendation,
            features_used=feature_row.to_dict(),
        )


# Module-level singleton — loaded once at app startup
strikeout_model = StrikeoutModel()

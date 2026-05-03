"""
/picks router — prediction endpoints for strikeout props.
"""
import numpy as np
import pandas as pd
from datetime import date
from fastapi import APIRouter, HTTPException

from app.schemas import PredictRequest, PredictionResponse, TodayPicksResponse, PickItem
from app.models.strikeout import strikeout_model
from app.models.features import assemble_feature_row, FEATURE_COLS
from app.data.fetch import lookup_pitcher_id, get_pitcher_statcast, get_season_pitching_stats

router = APIRouter(prefix="/picks", tags=["picks"])

MODEL_VERSION = "strikeout-xgb-v1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_edge(edge_pct: float) -> str:
    sign = "+" if edge_pct >= 0 else ""
    return f"{sign}{edge_pct * 100:.1f}%"


def _feature_dict(row: pd.Series) -> dict:
    def safe(key):
        v = row.get(key)
        return None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), 4)
    return {
        "k5":      safe("k_pct_last5"),
        "k15":     safe("k_pct_last15"),
        "ks":      safe("k_pct_season"),
        "ff":      safe("ff_pct"),
        "velo":    safe("ff_velo_avg"),
        "spin":    safe("ff_spin_avg"),
        "swstr":   safe("swstr_pct"),
        "ip5":     safe("avg_ip_last5"),
        "opp":     safe("opp_k_pct"),
        "lineup_opp": safe("opp_lineup_k_pct"),
        "matchup_score": safe("matchup_k_score"),
        "umpire":  safe("umpire_k_rate"),
    }


def _build_features_from_request(req: PredictRequest) -> pd.Series:
    """
    Build a feature row from the request.  Manual overrides take priority;
    if rolling stats are not supplied we fall back to the season-level
    pitching stats table (faster than pulling full Statcast for every call).
    """
    season = date.today().year

    # ---- Season-level fallback ----
    k_pct_season = req.k_pct_season
    k_pct_last5 = req.k_pct_last5
    k_pct_last15 = req.k_pct_last15
    avg_ip_last5 = req.avg_ip_last5
    opp_k_pct = req.opp_k_pct if req.opp_k_pct is not None else 0.22  # league-avg fallback

    if any(v is None for v in [k_pct_season, k_pct_last5, k_pct_last15, avg_ip_last5]):
        try:
            stats = get_season_pitching_stats(season)
            # pybaseball returns "Name" column with full name
            name_match = stats[stats["Name"].str.lower().str.contains(req.last_name.lower(), na=False)]
            if not name_match.empty:
                row = name_match.iloc[0]
                # SO% = SO / (SO + BB + H + ...) — approximate with SO/TBF
                if k_pct_season is None:
                    k_pct_season = row.get("K%", row.get("SO", 20) / max(row.get("TBF", 100), 1))
                if k_pct_last5 is None:
                    k_pct_last5 = k_pct_season  # best we can do without game-by-game log
                if k_pct_last15 is None:
                    k_pct_last15 = k_pct_season
                if avg_ip_last5 is None:
                    avg_ip_last5 = row.get("IP", 0) / max(row.get("G", 1), 1)
        except Exception:
            # Graceful degradation — use league averages
            k_pct_season = k_pct_season or 0.23
            k_pct_last5 = k_pct_last5 or 0.23
            k_pct_last15 = k_pct_last15 or 0.23
            avg_ip_last5 = avg_ip_last5 or 5.5

    # ---- Statcast pitch-mix (last 60 days) ----
    pitch_mix_features: dict = {}
    try:
        mlbam_id = lookup_pitcher_id(req.last_name, req.first_name)
        if mlbam_id:
            end = date.today().isoformat()
            start_dt = date(season, 3, 1).isoformat()
            sc_df = get_pitcher_statcast(mlbam_id, start_dt, end)
            from app.models.features import build_pitch_mix_features
            pitch_mix_features = build_pitch_mix_features(sc_df)
    except Exception:
        pass  # fall through to NaN defaults handled by XGBoost

    feature_dict = {
        "k_pct_last5": k_pct_last5,
        "k_pct_last15": k_pct_last15,
        "k_pct_season": k_pct_season,
        "avg_ip_last5": avg_ip_last5,
        "days_rest": req.days_rest,
        "opp_k_pct": opp_k_pct,
        "is_home": int(req.is_home),

        **pitch_mix_features,
    }

    return pd.Series({col: feature_dict.get(col, np.nan) for col in FEATURE_COLS})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/predict", response_model=PredictionResponse)
def predict_strikeouts(req: PredictRequest):
    """
    Predict expected strikeout total for a starting pitcher and calculate
    the edge vs. the sportsbook line.
    """
    try:
        features = _build_features_from_request(req)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Feature build failed: {e}")

    matchup = f"vs {req.opponent_team} @ {'home' if req.is_home else 'away'}"

    try:
        pred = strikeout_model.predict(
            feature_row=features,
            line=req.line,
            over_odds=req.over_odds,
            pitcher_name=req.pitcher_name,
            matchup=matchup,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return PredictionResponse(
        pitcher_name=pred.pitcher_name,
        matchup=pred.matchup,
        predicted_ks=pred.predicted_ks,
        line=pred.line,
        model_prob_over=pred.model_prob_over,
        implied_prob_over=pred.implied_prob_over,
        edge_pct=pred.edge_pct,
        edge_pct_display=_format_edge(pred.edge_pct),
        confidence=pred.confidence,
        recommendation=pred.recommendation,
        features=_feature_dict(features),
    )


@router.get("/today", response_model=TodayPicksResponse)
def today_picks():
    """
    Returns today's top K-prop edges using a curated slate of demo pitchers.
    In production this would pull from a scheduled pipeline that fetches
    the day's confirmed starters and runs them through the model automatically.
    """
    today = date.today().isoformat()

    # Demo slate — replace with live starter ingestion in next iteration
    demo_slate = [
        dict(pitcher_name="Gerrit Cole", last_name="Cole", first_name="Gerrit",
             opponent_team="BOS", park_team="NYY", is_home=True, days_rest=5,
             line=7.5, over_odds=-115,
             k_pct_last5=0.31, k_pct_last15=0.29, k_pct_season=0.28,
             avg_ip_last5=6.1, opp_k_pct=0.245),
        dict(pitcher_name="Spencer Strider", last_name="Strider", first_name="Spencer",
             opponent_team="LAD", park_team="ATL", is_home=True, days_rest=4,
             line=8.5, over_odds=-110,
             k_pct_last5=0.36, k_pct_last15=0.34, k_pct_season=0.35,
             avg_ip_last5=5.8, opp_k_pct=0.22),
        dict(pitcher_name="Pablo López", last_name="Lopez", first_name="Pablo",
             opponent_team="DET", park_team="MIN", is_home=True, days_rest=5,
             line=6.5, over_odds=-120,
             k_pct_last5=0.27, k_pct_last15=0.26, k_pct_season=0.25,
             avg_ip_last5=5.9, opp_k_pct=0.21),
        dict(pitcher_name="Kevin Gausman", last_name="Gausman", first_name="Kevin",
             opponent_team="SEA", park_team="SF", is_home=False, days_rest=5,
             line=6.5, over_odds=-105,
             k_pct_last5=0.29, k_pct_last15=0.28, k_pct_season=0.27,
             avg_ip_last5=5.7, opp_k_pct=0.235),
    ]

    picks: list[PickItem] = []
    for i, slate_item in enumerate(demo_slate):
        req = PredictRequest(**slate_item)
        try:
            features = _build_features_from_request(req)
            matchup = f"vs {req.opponent_team} @ {'home' if req.is_home else 'away'}"
            pred = strikeout_model.predict(
                feature_row=features,
                line=req.line,
                over_odds=req.over_odds,
                pitcher_name=req.pitcher_name,
                matchup=matchup,
            )
            bet_side = "Over" if pred.recommendation != "UNDER" else "Under"
            picks.append(PickItem(
                rank=i + 1,
                pitcher_name=pred.pitcher_name,
                matchup=pred.matchup,
                bet=f"{bet_side} {pred.line} K",
                predicted_ks=pred.predicted_ks,
                line=pred.line,
                edge_pct_display=_format_edge(pred.edge_pct),
                confidence=pred.confidence,
                recommendation=pred.recommendation,
                model_prob_over=pred.model_prob_over,
                implied_prob_over=pred.implied_prob_over,
                features=_feature_dict(features),
            ))
        except Exception:
            continue

    picks.sort(key=lambda p: abs(float(p.edge_pct_display.replace("%", "").replace("+", ""))), reverse=True)
    for i, p in enumerate(picks):
        p.rank = i + 1

    return TodayPicksResponse(date=today, picks=picks, model_version=MODEL_VERSION)

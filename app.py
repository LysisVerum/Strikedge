"""
mlbet — single entry point.

    python app.py

Starts a Flask server on http://localhost:5000 that:
  1. Loads the trained strikeout model
  2. Pulls today's probable starters from the MLB Stats API
  3. Builds real feature rows (rolling K%, pitch mix, opponent K%)
  4. Serves the React frontend (frontend/dist)
  5. Exposes /api/* routes

To rebuild the frontend after UI changes:
    cd frontend && npm run build

To rebuild the model on real data:
    cd backend && python -m train.build_dataset
    cd backend && python -m train.train_strikeout
"""
import os
import sys
import json
import math
import threading
import time
import warnings
from pathlib import Path
from datetime import date, datetime

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from flask import Flask, send_from_directory, jsonify, request, abort
from flask_cors import CORS
from dotenv import load_dotenv

import numpy as np
import pandas as pd

from backend.app.models.strikeout import strikeout_model
from backend.app.models.features import FEATURE_COLS
from backend.app.models.hitting import hitting_model, HITTING_FEATURE_COLS
from backend.app.data.mlb_api import (
    get_todays_starters,
    get_team_matchups_today,
    get_team_k_pct,
    get_pitcher_multi_season_log,
    get_team_id_map,
    search_pitcher,
    invalidate_schedule_cache,
    _ascii,
)
from backend.app.data.statcast_agg import get_pitcher_statcast_range, pitch_mix_features, invalidate_current_month
from backend.app.data.pipeline import build_inference_row
from backend.app.data.odds_api import get_sp_strikeout_lines, match_line_to_starter, get_credits_remaining, invalidate_player_prop_cache
from backend.app.data.umpire import get_todays_umpires
from backend.app.data.prediction_log import (
    log_predictions, get_live_record, update_results, delete_prediction,
    log_skipped, update_skipped_results, get_skipped_record,
)
from backend.app.data.k_log import log_slate_predictions, update_actuals, get_accuracy_stats
from backend.app.data.hitting_log import (
    log_hitting_predictions, get_hitting_live_record, update_hitting_results,
    delete_hitting_prediction, log_hitting_skipped,
    update_hitting_skipped_results, get_hitting_skipped_record,
)
from backend.app.data.hitting_pipeline import build_live_hitting_slate
from backend.app.db import init_db, purge_expired
from backend.app.auth import generate_magic_link, verify_magic_link, create_session, get_session_email, delete_session
from backend.app.users import get_user, upsert_user, get_tier, get_token_info, use_token, get_unlocked_today
from backend.app import stripe_handler

load_dotenv(Path(__file__).parent / "backend" / ".env")

# ---------------------------------------------------------------------------
# Seed static artifacts into the Railway volume on first boot.
# The volume at /app/backend/artifacts starts empty and overrides the files
# copied by the Dockerfile. Seed from backend/artifacts_seed/ if missing.
# ---------------------------------------------------------------------------
def _seed_artifacts():
    seed_dir    = Path(__file__).parent / "backend" / "artifacts_seed"
    target_dir  = Path(__file__).parent / "backend" / "artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)
    if not seed_dir.exists():
        return
    for src in seed_dir.iterdir():
        dst = target_dir / src.name
        if not dst.exists():
            import shutil
            shutil.copy2(src, dst)
            print(f"[seed] Copied {src.name} -> artifacts/")

_seed_artifacts()

FREE_PICKS_LIMIT   = 2     # picks shown to free-tier / unauthenticated users
MIN_EDGE_UNDER     = 0.10  # 10% edge required to surface an UNDER pick
MIN_EDGE_OVER      = 0.15  # 15% edge required to surface an OVER pick (higher bar)

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
MODEL_VERSION  = "strikeout-xgb-v1"

app = Flask(__name__, static_folder=None)
CORS(app)

_store = {
    "picks":         [],   # edge picks only (OVER>=15% or UNDER>=10%)
    "all_processed": [],   # every starter that went through the model
    "slate":         [],   # raw starters (MLB API + DK augmentation)
    "last_update":   None,
    "model_loaded":  False,
    "refresh_running": False,
}

_hitting_store = {
    "picks":         [],
    "all_processed": [],
    "last_update":   None,
    "model_loaded":  False,
}

_refresh_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Hitting demo slate — realistic 2025 batter feature rows.
# Replace with a live lineup pipeline when batter Statcast agg is ready.
# ---------------------------------------------------------------------------
_HITTING_DEMO_SLATE = [
    {
        "batter_name": "Juan Soto", "mlbam_id": 665742,
        "team": "NYY", "opponent_abbr": "BOS", "is_home": True,
        "line": 1.5, "over_odds": -120, "under_odds": 100,
        "features": {
            "h_per_pa_last7": 0.330, "h_per_pa_last14": 0.310,
            "h_per_pa_last30": 0.290, "h_per_pa_season": 0.285,
            "barrel_rate_last30": 0.115, "hard_hit_pct_last30": 0.510,
            "xba_last30": 0.305, "avg_exit_velo_last30": 93.4,
            "sweet_spot_pct_last30": 0.390, "pa_per_game_last14": 4.3,
            "h_per_pa_vs_hand_last60": 0.295,
            "opp_k_pct": 0.215, "opp_hard_hit_pct_allowed": 0.365,
            "opp_xba_allowed": 0.260, "park_factor": 0.97, "is_home": 1,
        },
    },
    {
        "batter_name": "Yordan Alvarez", "mlbam_id": 670541,
        "team": "HOU", "opponent_abbr": "OAK", "is_home": True,
        "line": 1.5, "over_odds": -110, "under_odds": -110,
        "features": {
            "h_per_pa_last7": 0.315, "h_per_pa_last14": 0.300,
            "h_per_pa_last30": 0.295, "h_per_pa_season": 0.290,
            "barrel_rate_last30": 0.142, "hard_hit_pct_last30": 0.565,
            "xba_last30": 0.320, "avg_exit_velo_last30": 95.8,
            "sweet_spot_pct_last30": 0.410, "pa_per_game_last14": 4.1,
            "h_per_pa_vs_hand_last60": 0.310,
            "opp_k_pct": 0.235, "opp_hard_hit_pct_allowed": 0.340,
            "opp_xba_allowed": 0.248, "park_factor": 1.04, "is_home": 1,
        },
    },
    {
        "batter_name": "Freddie Freeman", "mlbam_id": 518692,
        "team": "LAD", "opponent_abbr": "SF", "is_home": False,
        "line": 1.5, "over_odds": -115, "under_odds": -105,
        "features": {
            "h_per_pa_last7": 0.305, "h_per_pa_last14": 0.295,
            "h_per_pa_last30": 0.285, "h_per_pa_season": 0.280,
            "barrel_rate_last30": 0.098, "hard_hit_pct_last30": 0.480,
            "xba_last30": 0.298, "avg_exit_velo_last30": 92.1,
            "sweet_spot_pct_last30": 0.375, "pa_per_game_last14": 4.4,
            "h_per_pa_vs_hand_last60": 0.290,
            "opp_k_pct": 0.225, "opp_hard_hit_pct_allowed": 0.350,
            "opp_xba_allowed": 0.255, "park_factor": 1.01, "is_home": 0,
        },
    },
    {
        "batter_name": "Mookie Betts", "mlbam_id": 605141,
        "team": "LAD", "opponent_abbr": "SF", "is_home": False,
        "line": 0.5, "over_odds": -185, "under_odds": 155,
        "features": {
            "h_per_pa_last7": 0.280, "h_per_pa_last14": 0.270,
            "h_per_pa_last30": 0.265, "h_per_pa_season": 0.270,
            "barrel_rate_last30": 0.108, "hard_hit_pct_last30": 0.465,
            "xba_last30": 0.285, "avg_exit_velo_last30": 91.7,
            "sweet_spot_pct_last30": 0.355, "pa_per_game_last14": 4.2,
            "h_per_pa_vs_hand_last60": 0.275,
            "opp_k_pct": 0.225, "opp_hard_hit_pct_allowed": 0.350,
            "opp_xba_allowed": 0.255, "park_factor": 1.01, "is_home": 0,
        },
    },
    {
        "batter_name": "Rafael Devers", "mlbam_id": 646240,
        "team": "BOS", "opponent_abbr": "NYY", "is_home": False,
        "line": 1.5, "over_odds": -115, "under_odds": -105,
        "features": {
            "h_per_pa_last7": 0.265, "h_per_pa_last14": 0.270,
            "h_per_pa_last30": 0.275, "h_per_pa_season": 0.268,
            "barrel_rate_last30": 0.132, "hard_hit_pct_last30": 0.530,
            "xba_last30": 0.293, "avg_exit_velo_last30": 94.2,
            "sweet_spot_pct_last30": 0.362, "pa_per_game_last14": 4.0,
            "h_per_pa_vs_hand_last60": 0.285,
            "opp_k_pct": 0.235, "opp_hard_hit_pct_allowed": 0.355,
            "opp_xba_allowed": 0.263, "park_factor": 0.97, "is_home": 0,
        },
    },
    {
        "batter_name": "Fernando Tatis Jr.", "mlbam_id": 665487,
        "team": "SD", "opponent_abbr": "ARI", "is_home": True,
        "line": 0.5, "over_odds": -175, "under_odds": 145,
        "features": {
            "h_per_pa_last7": 0.255, "h_per_pa_last14": 0.262,
            "h_per_pa_last30": 0.268, "h_per_pa_season": 0.260,
            "barrel_rate_last30": 0.120, "hard_hit_pct_last30": 0.490,
            "xba_last30": 0.278, "avg_exit_velo_last30": 92.8,
            "sweet_spot_pct_last30": 0.345, "pa_per_game_last14": 4.3,
            "h_per_pa_vs_hand_last60": 0.272,
            "opp_k_pct": 0.245, "opp_hard_hit_pct_allowed": 0.360,
            "opp_xba_allowed": 0.252, "park_factor": 0.96, "is_home": 1,
        },
    },
    {
        "batter_name": "Paul Goldschmidt", "mlbam_id": 502671,
        "team": "STL", "opponent_abbr": "CHC", "is_home": True,
        "line": 1.5, "over_odds": -110, "under_odds": -110,
        "features": {
            "h_per_pa_last7": 0.252, "h_per_pa_last14": 0.258,
            "h_per_pa_last30": 0.262, "h_per_pa_season": 0.255,
            "barrel_rate_last30": 0.106, "hard_hit_pct_last30": 0.455,
            "xba_last30": 0.275, "avg_exit_velo_last30": 91.3,
            "sweet_spot_pct_last30": 0.348, "pa_per_game_last14": 4.1,
            "h_per_pa_vs_hand_last60": 0.268,
            "opp_k_pct": 0.218, "opp_hard_hit_pct_allowed": 0.372,
            "opp_xba_allowed": 0.265, "park_factor": 1.00, "is_home": 1,
        },
    },
    {
        "batter_name": "Matt Olson", "mlbam_id": 621566,
        "team": "ATL", "opponent_abbr": "MIA", "is_home": True,
        "line": 1.5, "over_odds": -115, "under_odds": -105,
        "features": {
            "h_per_pa_last7": 0.240, "h_per_pa_last14": 0.245,
            "h_per_pa_last30": 0.250, "h_per_pa_season": 0.248,
            "barrel_rate_last30": 0.125, "hard_hit_pct_last30": 0.505,
            "xba_last30": 0.272, "avg_exit_velo_last30": 93.0,
            "sweet_spot_pct_last30": 0.358, "pa_per_game_last14": 4.0,
            "h_per_pa_vs_hand_last60": 0.258,
            "opp_k_pct": 0.242, "opp_hard_hit_pct_allowed": 0.345,
            "opp_xba_allowed": 0.245, "park_factor": 1.03, "is_home": 1,
        },
    },
]


# ---------------------------------------------------------------------------
# Feature building
# ---------------------------------------------------------------------------

def _format_edge(edge: float) -> str:
    return f"+{edge*100:.1f}%" if edge >= 0 else f"{edge*100:.1f}%"


def _build_features_from_starter(starter: dict, team_k_map: dict, game_date: str, umpire_id: int = None) -> pd.Series:
    """Build a real feature row for a probable starter using live data."""
    season = int(game_date[:4])
    return build_inference_row(
        mlbam_id        = starter["mlbam_id"],
        game_date       = game_date,
        opponent_id     = starter["opponent_id"],
        is_home         = starter["is_home"],
        season          = season,
        _team_k_cache   = team_k_map,
        umpire_id       = umpire_id,
        opponent_abbr   = starter.get("opponent_abbr", ""),
        opp_lineup_ids  = starter.get("opp_lineup_ids", []),
    )


def _build_features_manual(body: dict) -> pd.Series:
    """Build features from a manual predict request (pitcher search / quick line)."""
    season   = date.today().year
    game_date = date.today().isoformat()

    mlbam_id = body.get("mlbam_id")

    # Try pipeline first if we have an MLBAM ID
    if mlbam_id:
        try:
            team_k = get_team_k_pct(season)
            team_map = get_team_id_map(season)
            opp_id  = team_map.get(body.get("opponent_team", ""), None)
            return build_inference_row(
                mlbam_id      = mlbam_id,
                game_date     = game_date,
                opponent_id   = opp_id,
                is_home       = bool(body.get("is_home", True)),
                season        = season,
                _team_k_cache = team_k,
                opponent_abbr = body.get("opponent_team", ""),
            )
        except Exception:
            pass

    # Fallback: use manually supplied stats
    fd = {
        "k_pct_last5":  body.get("k_pct_last5")  or 0.23,
        "k_pct_last15": body.get("k_pct_last15") or 0.23,
        "k_pct_season": body.get("k_pct_season") or 0.23,
        "avg_ip_last5": body.get("avg_ip_last5") or 5.5,
        "ff_pct":       body.get("ff_pct",      np.nan),
        "ff_velo_avg":  body.get("ff_velo_avg", np.nan),
        "ff_spin_avg":  body.get("ff_spin_avg", np.nan),
        "opp_k_pct":    body.get("opp_k_pct")  or 0.225,
    }
    return pd.Series({col: fd.get(col, np.nan) for col in FEATURE_COLS})


# ---------------------------------------------------------------------------
# Slate runner
# ---------------------------------------------------------------------------

def _kelly_bet(model_prob_win: float, odds: int, bankroll: float = 1000.0, kelly_frac: float = 0.25) -> float:
    """Quarter-Kelly bet sizing capped at bankroll."""
    b = (100 / abs(odds)) if odds < 0 else (odds / 100)
    q = 1 - model_prob_win
    k = (model_prob_win * b - q) / b
    if k <= 0:
        return 0.0
    return round(min(k * kelly_frac * bankroll, bankroll), 0)


def _safe(v, default=None):
    """Convert a value to float, returning default if NaN/inf/None."""
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _augment_from_lines(starters: list[dict], live_lines: dict, season: int, game_date: str = None) -> list[dict]:
    """
    Add pitchers that DraftKings has K props for but that aren't in the MLB API probable starters.
    DK only lists props for confirmed starters, so this fills the gap when the MLB API lags.
    Resolves MLBAM IDs via the season leaderboard and fills opponent info from today's schedule.
    """
    if not live_lines:
        return starters

    # Fetch full schedule matchups (all games, regardless of probable pitcher status)
    try:
        matchup_map = get_team_matchups_today(game_date)
    except Exception as e:
        print(f"  [augment] Could not fetch team matchups: {e} — opponent info will be league avg")
        matchup_map = {}

    # Index existing starters by ASCII last name for fast dedup
    covered = {_ascii(s["pitcher_name"]).split()[-1] for s in starters}

    added = 0
    for dk_name in live_lines:
        dk_last = dk_name.split()[-1]
        if dk_last in covered:
            continue

        # Try current season first, then prior season (handles callups mid-season)
        matches = search_pitcher(dk_name, season) or search_pitcher(dk_name, season - 1)
        if not matches:
            print(f"  [augment] {dk_name}: MLBAM ID not found in leaderboard — skipping")
            continue

        best    = matches[0]
        opp     = matchup_map.get(best["team"], {})
        if not opp:
            print(f"  [augment] {best['full_name']} ({best['team']}): no game today per schedule — stale DK prop, skipping")
            continue
        starters.append({
            "pitcher_name":  best["full_name"],
            "mlbam_id":      best["mlbam_id"],
            "team":          best["team"],
            "team_id":       None,
            "opponent_name": opp.get("opponent_name", "Unknown"),
            "opponent_abbr": opp.get("opponent_abbr", "???"),
            "opponent_id":   opp.get("opponent_id"),
            "park_team":     best["team"] if opp.get("is_home") else opp.get("opponent_abbr", best["team"]),
            "is_home":       opp.get("is_home", True),
            "game_time":     opp.get("game_time", ""),
            "opp_lineup_ids": [],
        })
        covered.add(dk_last)
        added += 1
        opp_label = opp.get("opponent_abbr", "???")
        print(f"  [augment] {best['full_name']} ({best['team']} vs {opp_label}) added from DK lines")

    if added:
        print(f"[mlbet] Augmented slate: +{added} pitchers from DK lines")
    return starters


def _run_slate(starters: list[dict], team_k_map: dict, game_date: str, live_lines: dict = None, umpire_map: dict = None) -> list:
    picks = []
    live_lines = live_lines or {}
    umpire_map = umpire_map or {}

    for starter in starters:
        name = starter["pitcher_name"]
        try:
            umpire_id = umpire_map.get(starter.get("game_pk"))
            features = _build_features_from_starter(starter, team_k_map, game_date, umpire_id=umpire_id)

            # Skip pitchers with no qualifying start history — model defaults aren't reliable enough to bet
            if pd.isna(features.get("k_pct_last5")) or pd.isna(features.get("k_pct_last15")):
                print(f"  [skip] {name}: insufficient K-rate history — omitting from slate")
                continue

            matchup  = f"vs {starter['opponent_abbr']} @ {'home' if starter['is_home'] else 'away'}"

            # Use live sportsbook line if available, else fall back to model-projected line
            odds_entry = match_line_to_starter(name, live_lines)
            if odds_entry:
                line       = odds_entry["line"]
                over_odds  = odds_entry["over_odds"]
                under_odds = odds_entry.get("under_odds", -over_odds)
                line_src   = odds_entry["book"]
                has_live   = True
            else:
                _preview   = strikeout_model.predict(features, line=5.5, pitcher_name=name, matchup=matchup)
                line       = round(_preview.predicted_ks * 2 - 0.5) / 2
                line       = max(3.5, min(line, 12.5))
                over_odds  = -115
                under_odds = -115
                line_src   = "model"
                has_live   = False

            pred = strikeout_model.predict(
                feature_row  = features,
                line         = line,
                over_odds    = over_odds,
                under_odds   = under_odds,
                pitcher_name = name,
                matchup      = matchup,
            )
            fv   = pred.features_used
            side = "Under" if pred.recommendation == "UNDER" else "Over"

            if pred.recommendation == "OVER":
                model_prob_win = pred.model_prob_over
                bet_odds       = over_odds
            elif pred.recommendation == "UNDER":
                model_prob_win = 1 - pred.model_prob_over
                bet_odds       = under_odds
            else:
                model_prob_win = 0.0
                bet_odds       = over_odds
            recommended_bet = _kelly_bet(model_prob_win, bet_odds)

            picks.append({
                "rank":              0,
                "has_line":          True,
                "live_line":         has_live,
                "mlbam_id":          starter.get("mlbam_id", 0),
                "pitcher_name":      pred.pitcher_name,
                "matchup":           pred.matchup,
                "bet":               f"{side} {pred.line} K",
                "predicted_ks":      pred.predicted_ks,
                "line":              pred.line,
                "line_source":       line_src,
                "over_odds":         over_odds,
                "under_odds":        under_odds,
                "bet_odds":          bet_odds,
                "edge_pct_display":  _format_edge(pred.edge_pct),
                "edge_pct":          pred.edge_pct,
                "confidence":        pred.confidence,
                "recommendation":    pred.recommendation,
                "model_prob_over":   pred.model_prob_over,
                "implied_prob_over": pred.implied_prob_over,
                "team":              starter.get("team", ""),
                "opponent":          starter.get("opponent_abbr", ""),
                "recommended_bet":   recommended_bet,
                "features": {
                    "k5":            _safe(fv.get("k_pct_last5")),
                    "k15":           _safe(fv.get("k_pct_last15")),
                    "ks":            _safe(fv.get("k_pct_season")),
                    "fip":           _safe(fv.get("fip_last15")),
                    "ip5":           _safe(fv.get("avg_ip_last5")),
                    "ff":            _safe(fv.get("ff_pct")),
                    "velo":          _safe(fv.get("ff_velo_avg")),
                    "spin":          _safe(fv.get("ff_spin_avg")),
                    "swstr":         _safe(fv.get("swstr_pct")),
                    "whiff":         _safe(fv.get("whiff_pct")),
                    "csw":           _safe(fv.get("csw_pct")),
                    "opp":           _safe(fv.get("opp_k_pct"), 0.225),
                    "lineup_opp":    _safe(fv.get("opp_lineup_k_pct")),
                    "matchup_score": _safe(fv.get("matchup_k_score")),
                    "umpire":        _safe(fv.get("umpire_k_rate")),
                },
            })
        except Exception as e:
            print(f"  [warn] {name}: {e}")

    meaningful = [
        p for p in picks
        if (p["recommendation"] == "UNDER" and abs(p["edge_pct"]) >= MIN_EDGE_UNDER)
        or (p["recommendation"] == "OVER"  and abs(p["edge_pct"]) >= MIN_EDGE_OVER)
    ]
    meaningful.sort(key=lambda p: abs(p["edge_pct"]), reverse=True)
    for i, p in enumerate(meaningful):
        p["rank"] = i + 1

    # All processed picks sorted by abs(edge), for premium full-slate view
    picks.sort(key=lambda p: abs(p["edge_pct"]), reverse=True)
    meaningful_names = {p["pitcher_name"] for p in meaningful}
    for p in picks:
        p["actionable"] = p["pitcher_name"] in meaningful_names

    return meaningful, picks


def _run_hitting_slate(slate: list[dict]) -> tuple[list, list]:
    """
    Run the hitting model over the batter slate.
    Returns (edge_picks, all_processed) — same contract as _run_slate().
    Batters with has_line=False are included in all_processed for model projections
    but are never surfaced as edge picks or given a bet recommendation.
    """
    import numpy as np
    picks = []
    for batter in slate:
        name     = batter["batter_name"]
        has_line = batter.get("has_line", True)
        try:
            fv   = batter["features"]
            row  = pd.Series({col: fv.get(col, np.nan) for col in HITTING_FEATURE_COLS})
            matchup = f"vs {batter['opponent_abbr']} @ {'home' if batter['is_home'] else 'away'}"

            line       = batter["line"]
            over_odds  = batter["over_odds"]
            under_odds = batter["under_odds"]

            pred = hitting_model.predict(
                feature_row  = row,
                line         = line,
                over_odds    = over_odds,
                under_odds   = under_odds,
                batter_name  = name,
                matchup      = matchup,
            )

            # Force PASS for batters without a real DK line — model has no real implied prob
            # Also force PASS for Under on 0.5-line: DK only offers "1+" (at-least-1-hit)
            # as an Over-side bet; the Under (zero hits) is not a standard available market
            recommendation = "PASS" if not has_line else pred.recommendation
            if recommendation == "UNDER" and line <= 0.5:
                recommendation = "PASS"
            edge_pct = pred.edge_pct if (has_line and recommendation != "PASS") else 0.0

            if recommendation == "OVER":
                model_prob_win = pred.model_prob_over
                bet_odds       = over_odds
            elif recommendation == "UNDER":
                model_prob_win = 1 - pred.model_prob_over
                bet_odds       = under_odds
            else:
                model_prob_win = 0.0
                bet_odds       = over_odds

            recommended_bet = _kelly_bet(model_prob_win, bet_odds) if has_line else 0
            # Use DK-style display: "1+ H", "2+ H" for Over; "Under 2 H" for Under
            line_val = pred.line
            if recommendation == "UNDER":
                side = f"Under {int(line_val + 0.5)} H"
            else:
                side = f"{int(line_val + 0.5)}+ H"

            picks.append({
                "rank":              0,
                "has_line":          has_line,
                "live_line":         False,
                "mlbam_id":          batter["mlbam_id"],
                "batter_name":       pred.batter_name,
                "matchup":           pred.matchup,
                "team":              batter.get("team", ""),
                "opponent":          batter.get("opponent_abbr", ""),
                "bet":               side,
                "predicted_hits":    pred.predicted_hits,
                "line":              pred.line,
                "line_source":       batter.get("book", "DraftKings") if has_line else "model",
                "over_odds":         over_odds,
                "under_odds":        under_odds,
                "bet_odds":          bet_odds,
                "edge_pct_display":  _format_edge(edge_pct),
                "edge_pct":          edge_pct,
                "confidence":        pred.confidence if has_line else "LOW",
                "recommendation":    recommendation,
                "model_prob_over":   pred.model_prob_over,
                "implied_prob_over": pred.implied_prob_over,
                "recommended_bet":   recommended_bet,
                "features": {
                    "h7":       _safe(fv.get("h_per_pa_last7")),
                    "h14":      _safe(fv.get("h_per_pa_last14")),
                    "h30":      _safe(fv.get("h_per_pa_last30")),
                    "h60":      _safe(fv.get("_h60")),
                    "h90":      _safe(fv.get("_h90")),
                    "hs":       _safe(fv.get("h_per_pa_season")),
                    "barrel":   _safe(fv.get("barrel_rate_last30")),
                    "hard_hit": _safe(fv.get("hard_hit_pct_last30")),
                    "xba":      _safe(fv.get("xba_last30")),
                    "exit_velo":_safe(fv.get("avg_exit_velo_last30")),
                    "sweet_spot": _safe(fv.get("sweet_spot_pct_last30")),
                    "pa_rate":  _safe(fv.get("pa_per_game_last14")),
                    "vs_hand":  _safe(fv.get("h_per_pa_vs_hand_last60")),
                    "opp_k":    _safe(fv.get("opp_k_pct"), 0.225),
                    "opp_hard_hit": _safe(fv.get("opp_hard_hit_pct_allowed")),
                    "opp_xba":  _safe(fv.get("opp_xba_allowed")),
                    "park":     _safe(fv.get("park_factor"), 1.0),
                },
            })
        except Exception as e:
            print(f"  [hitting] {name}: {e}")

    meaningful = [
        p for p in picks
        if p.get("has_line", True)
        and (
            (p["recommendation"] == "UNDER" and abs(p["edge_pct"]) >= MIN_EDGE_UNDER)
            or (p["recommendation"] == "OVER"  and abs(p["edge_pct"]) >= MIN_EDGE_OVER)
        )
    ]
    meaningful.sort(key=lambda p: abs(p["edge_pct"]), reverse=True)
    for i, p in enumerate(meaningful):
        p["rank"] = i + 1

    # Sort: has-line batters by edge desc, then no-line batters at bottom
    picks.sort(key=lambda p: (0 if p.get("has_line", True) else 1, -abs(p["edge_pct"])))
    meaningful_names = {p["batter_name"] for p in meaningful}
    for p in picks:
        p["actionable"] = p["batter_name"] in meaningful_names

    return meaningful, picks


def _background_maintenance(interval_seconds=3600):
    while True:
        time.sleep(interval_seconds)
        try:
            purge_expired()
        except Exception as e:
            print(f"[db] purge_expired error: {e}")
        try:
            refresh_data()
        except Exception as e:
            print(f"[maintenance] refresh_data error: {e}")


def refresh_data(force_odds_refresh: bool = False):
    if not _refresh_lock.acquire(blocking=False):
        print("[mlbet] refresh_data already running — skipping duplicate call")
        return
    _store["refresh_running"] = True
    try:
        _refresh_data_inner(force_odds_refresh)
    finally:
        _store["refresh_running"] = False
        _refresh_lock.release()


def _refresh_data_inner(force_odds_refresh: bool = False):
    print("[mlbet] Loading model...")
    try:
        strikeout_model.load()
        _store["model_loaded"] = True
        print("[mlbet] Model loaded.")
    except FileNotFoundError:
        print("[mlbet] Model not found -- run: cd backend && python -m train.train_strikeout")
        return

    invalidate_current_month()

    game_date = date.today().isoformat()
    season    = date.today().year

    print(f"[mlbet] Fetching today's starters ({game_date})...")
    try:
        starters = get_todays_starters(game_date)
        print(f"[mlbet] {len(starters)} probable starters found by MLB API.")
    except Exception as e:
        print(f"[mlbet] Could not fetch starters: {e}")
        starters = []

    print("[mlbet] Fetching live strikeout lines...")
    try:
        live_lines = get_sp_strikeout_lines(force_refresh=force_odds_refresh)
        print(f"[mlbet] {len(live_lines)} live lines loaded.")
    except Exception as e:
        print(f"[mlbet] Could not fetch live lines: {e} — using model lines")
        live_lines = {}

    # Fill in starters that DK has lines for but MLB API hasn't announced yet
    starters = _augment_from_lines(starters, live_lines, season, game_date)
    print(f"[mlbet] {len(starters)} total starters after DK augmentation.")

    if not starters:
        print("[mlbet] No starters available — picks list will be empty.")
        _store["picks"]       = []
        _store["slate"]       = []
        _store["last_update"] = datetime.now().isoformat(timespec="seconds")
        return

    print("[mlbet] Fetching team K% data...")
    try:
        team_k_map = get_team_k_pct(season)
    except Exception as e:
        print(f"[mlbet] Could not fetch team K%: {e} — using league avg")
        team_k_map = {}

    print("[mlbet] Fetching today's umpires...")
    try:
        umpire_map = get_todays_umpires(game_date)
        print(f"[mlbet] {len(umpire_map)} umpires fetched.")
    except Exception as e:
        print(f"[mlbet] Could not fetch umpires: {e}")
        umpire_map = {}

    print("[mlbet] Building feature rows and running model...")
    try:
        picks, all_processed = _run_slate(starters, team_k_map, game_date, live_lines, umpire_map)
    except Exception as e:
        print(f"[mlbet] _run_slate error: {e}")
        picks = []
        all_processed = []

    _store["picks"]         = picks
    _store["all_processed"] = all_processed
    _store["slate"]         = starters
    _store["last_update"]   = datetime.now().isoformat(timespec="seconds")
    print(f"[mlbet] {len(picks)} picks ready. Updated: {_store['last_update']}")

    # Auto-log K predictions for accuracy tracking (no lines needed)
    logged = log_slate_predictions(game_date, picks)
    print(f"[mlbet] {logged} K predictions logged for accuracy tracking.")

    # Auto-log picks with live sportsbook lines to the bet log (deduped by pitcher+date)
    live_picks = [p for p in picks if p.get("live_line")]
    if live_picks:
        log_entries = [{
            "pitcher_name":    p["pitcher_name"],
            "mlbam_id":        p.get("mlbam_id", 0),
            "line":            p["line"],
            "over_odds":       p["over_odds"],
            "under_odds":      p.get("under_odds", -p["over_odds"]),
            "bet_odds":        p.get("bet_odds", p["over_odds"]),
            "line_source":     p["line_source"],
            "predicted_ks":    p["predicted_ks"],
            "recommendation":  p["recommendation"],
            "edge":            round(p["edge_pct"], 4),
            "confidence":      p["confidence"],
            "model_prob_over": p["model_prob_over"],
            "bet":             p["recommended_bet"],
            "features":        p.get("features", {}),
        } for p in live_picks]
        auto_logged = log_predictions(log_entries)
        print(f"[mlbet] {auto_logged} picks auto-logged to bet log.")

    # ---- Hitting model -------------------------------------------------------
    if not hitting_model.is_loaded:
        print("[mlbet] Loading hitting model...")
        try:
            hitting_model.load()
            _hitting_store["model_loaded"] = True
            print("[mlbet] Hitting model loaded.")
        except FileNotFoundError:
            print("[mlbet] Hitting model not found — run: cd backend && python -m train.train_hitting")
    else:
        _hitting_store["model_loaded"] = True

    if _hitting_store["model_loaded"]:
        print("[mlbet] Running hitting slate...")
        try:
            live_h_slate = build_live_hitting_slate(game_date) or []
        except Exception as e:
            print(f"[mlbet] hitting_pipeline error: {e}")
            live_h_slate = []
        try:
            h_picks, h_all = _run_hitting_slate(live_h_slate)
        except Exception as e:
            print(f"[mlbet] _run_hitting_slate error: {e}")
            h_picks, h_all = [], []
        _hitting_store["picks"]         = h_picks
        _hitting_store["all_processed"] = h_all
        _hitting_store["last_update"]   = _store["last_update"]
        print(f"[mlbet] {len(h_picks)} hitting picks ready.")

        live_h_picks = [p for p in h_picks if p.get("live_line")]
        if live_h_picks:
            h_log_entries = [{
                "batter_name":     p["batter_name"],
                "mlbam_id":        p["mlbam_id"],
                "line":            p["line"],
                "over_odds":       p["over_odds"],
                "under_odds":      p["under_odds"],
                "bet_odds":        p["bet_odds"],
                "line_source":     p["line_source"],
                "predicted_hits":  p["predicted_hits"],
                "recommendation":  p["recommendation"],
                "edge":            round(p["edge_pct"], 4),
                "confidence":      p["confidence"],
                "model_prob_over": p["model_prob_over"],
                "bet":             p["recommended_bet"],
                "features":        p.get("features", {}),
            } for p in live_h_picks]
            log_hitting_predictions(h_log_entries)

        h_actionable = {p["batter_name"] for p in h_picks}
        h_skipped = [p for p in h_all if p["batter_name"] not in h_actionable]
        if h_skipped:
            def _h_skip_reason(p):
                rec, edge = p["recommendation"], abs(p["edge_pct"])
                if rec == "PASS":
                    return f"PASS — {p['confidence']} conf, {edge*100:.1f}% edge"
                if rec == "UNDER":
                    return f"UNDER edge {edge*100:.1f}% < {MIN_EDGE_UNDER*100:.0f}% threshold"
                return f"OVER edge {edge*100:.1f}% < {MIN_EDGE_OVER*100:.0f}% threshold"
            log_hitting_skipped([{
                "batter_name":     p["batter_name"],
                "mlbam_id":        p["mlbam_id"],
                "line":            p["line"],
                "over_odds":       p["over_odds"],
                "under_odds":      p["under_odds"],
                "predicted_hits":  p["predicted_hits"],
                "recommendation":  p["recommendation"],
                "edge":            round(p["edge_pct"], 4),
                "confidence":      p["confidence"],
                "model_prob_over": p["model_prob_over"],
                "implied_prob_over": p.get("implied_prob_over"),
                "features":        p.get("features", {}),
                "skip_reason":     _h_skip_reason(p),
            } for p in h_skipped])
    # ---- End hitting model ---------------------------------------------------

    # Auto-log non-edge picks with live lines to skipped (deduped by pitcher+date)
    actionable_names = {p["pitcher_name"] for p in picks}
    skipped_live = [p for p in all_processed if p.get("live_line") and p["pitcher_name"] not in actionable_names]
    if skipped_live:
        def _skip_reason(p):
            rec, edge = p["recommendation"], abs(p["edge_pct"])
            if rec == "PASS":
                return f"PASS — {p['confidence']} conf, {edge*100:.1f}% edge"
            if rec == "UNDER":
                return f"UNDER edge {edge*100:.1f}% < {MIN_EDGE_UNDER*100:.0f}% threshold"
            return f"OVER edge {edge*100:.1f}% < {MIN_EDGE_OVER*100:.0f}% threshold"

        skip_entries = [{
            "pitcher_name":     p["pitcher_name"],
            "mlbam_id":         p.get("mlbam_id", 0),
            "line":             p["line"],
            "over_odds":        p["over_odds"],
            "under_odds":       p.get("under_odds", -p["over_odds"]),
            "predicted_ks":     p["predicted_ks"],
            "recommendation":   p["recommendation"],
            "edge":             round(p["edge_pct"], 4),
            "confidence":       p["confidence"],
            "model_prob_over":  p["model_prob_over"],
            "implied_prob_over": p.get("implied_prob_over"),
            "features":         p.get("features", {}),
            "skip_reason":      _skip_reason(p),
        } for p in skipped_live]
        auto_skipped = log_skipped(skip_entries)
        print(f"[mlbet] {auto_skipped} non-edge picks auto-logged to skipped.")




# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_session_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def _current_email() -> str | None:
    token = _get_session_token()
    return get_session_email(token) if token else None


def _current_tier() -> str:
    email = _current_email()
    return get_tier(email) if email else "free"


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

# ---- Auth ------------------------------------------------------------------

@app.post("/api/auth/magic-link")
def auth_magic_link():
    body  = request.get_json(force=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        abort(400, "Valid email required")
    try:
        upsert_user(email)
        generate_magic_link(email)
        return jsonify({"status": "sent"})
    except Exception as e:
        print(f"[auth] magic-link error for {email}: {e}")
        abort(500, "Could not send login email. Check RESEND_API_KEY and domain setup.")


@app.get("/api/auth/verify")
def auth_verify():
    token = request.args.get("token", "").strip()
    if not token:
        abort(400, "Token required")
    email = verify_magic_link(token)
    if not email:
        abort(401, "Token invalid or expired")
    session_token = create_session(email)
    user = get_user(email) or {}
    return jsonify({
        "session_token": session_token,
        "email":         email,
        "tier":          user.get("tier", "free"),
    })


@app.get("/api/auth/me")
def auth_me():
    email = _current_email()
    if not email:
        abort(401, "Not authenticated")
    user = get_user(email) or {"email": email, "tier": "free"}
    return jsonify({"email": email, "tier": user.get("tier", "free")})


@app.post("/api/auth/logout")
def auth_logout():
    token = _get_session_token()
    if token:
        delete_session(token)
    return jsonify({"status": "logged out"})


# ---- Admin -----------------------------------------------------------------

@app.post("/api/admin/set-premium")
def admin_set_premium():
    body      = request.get_json(force=True) or {}
    admin_key = body.get("key", "")
    email     = body.get("email", "").strip().lower()
    expected  = os.environ.get("ADMIN_KEY", "")
    if not expected or admin_key != expected:
        abort(403, "Forbidden")
    if not email:
        abort(400, "email required")
    from datetime import timezone, timedelta
    expires = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()
    from backend.app.users import set_premium
    set_premium(email,
                stripe_customer_id     = "manual",
                stripe_subscription_id = "manual",
                expires_at             = expires)
    return jsonify({"status": "ok", "email": email, "tier": "premium", "expires": expires})


# ---- Stripe ----------------------------------------------------------------

@app.post("/api/stripe/checkout")
def stripe_checkout():
    email = _current_email()
    if not email:
        abort(401, "Not authenticated")
    app_url     = request.host_url.rstrip("/")
    success_url = f"{app_url}/dashboard?upgrade=success"
    cancel_url  = f"{app_url}/dashboard"
    try:
        checkout_url = stripe_handler.create_checkout_session(email, success_url, cancel_url)
        return jsonify({"url": checkout_url})
    except Exception as e:
        print(f"[stripe] checkout error: {e}")
        abort(500, "Could not create checkout session")


@app.post("/api/stripe/webhook")
def stripe_webhook():
    payload    = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    result     = stripe_handler.handle_webhook(payload, sig_header)
    if "error" in result:
        abort(400, result["error"])
    return jsonify(result)


@app.get("/api/health")
def health():
    return jsonify({
        "status":                "ok",
        "model_loaded":          _store["model_loaded"],
        "last_update":           _store["last_update"],
        "n_picks":               len(_store["picks"]),
        "n_starters":            len(_store["slate"]),
        "refresh_running":       _store["refresh_running"],
        "odds_credits_remaining": get_credits_remaining(),
    })


@app.get("/api/picks/today")
def today_picks():
    email    = _current_email()
    tier     = get_tier(email) if email else "free"
    all_picks = _store["picks"]
    date_str  = date.today().isoformat()

    if tier == "premium":
        # Edge picks first, then PASS picks dimmed on the frontend
        edge_names = {p["pitcher_name"] for p in all_picks}
        pass_picks = [p for p in _store["all_processed"] if p["pitcher_name"] not in edge_names]
        return jsonify({
            "date":          date_str,
            "picks":         all_picks + pass_picks,
            "total_picks":   len(all_picks),
            "tier":          "premium",
            "model_version": MODEL_VERSION,
            "last_update":   _store["last_update"],
        })

    # Free tier — return all picks but lock unrevealed ones
    unlocked   = get_unlocked_today(email, date_str) if email else []
    token_info = get_token_info(email) if email else {"tokens_remaining": 0, "tokens_reset_at": None}

    picks_out = []
    pick_names = {p["pitcher_name"] for p in all_picks}
    for pick in all_picks:
        if pick["pitcher_name"] in unlocked:
            picks_out.append({**pick, "locked": False})
        else:
            picks_out.append({
                "pitcher_name": pick["pitcher_name"],
                "matchup":      pick.get("matchup", ""),
                "team":         pick.get("team", ""),
                "opponent":     pick.get("opponent", ""),
                "has_line":     pick.get("has_line", True),
                "locked":       True,
            })

    # Append remaining starters with no edge so free users see the full slate
    for starter in _store.get("slate", []):
        name = starter.get("pitcher_name") or starter.get("full_name") or starter.get("name", "")
        if name and name not in pick_names:
            team    = starter.get("team", "")
            opp     = starter.get("opponent_abbr") or starter.get("opponent_name", "")
            matchup = f"{team} vs {opp}" if team and opp else (starter.get("matchup", ""))
            picks_out.append({
                "pitcher_name": name,
                "matchup":      matchup,
                "team":         team,
                "has_line":     False,
                "locked":       True,
                "no_edge":      True,
            })

    return jsonify({
        "date":             date_str,
        "picks":            picks_out,
        "total_picks":      len(all_picks),
        "tier":             "free",
        "tokens_remaining": token_info["tokens_remaining"],
        "tokens_reset_at":  token_info["tokens_reset_at"],
        "model_version":    MODEL_VERSION,
        "last_update":      _store["last_update"],
    })


@app.post("/api/picks/unlock")
def unlock_pick():
    email = _current_email()
    if not email:
        abort(401, "Sign in required")
    if get_tier(email) == "premium":
        abort(400, "Premium users have full access — no token needed")

    body         = request.get_json(force=True) or {}
    pitcher_name = body.get("pitcher_name", "").strip()
    if not pitcher_name:
        abort(400, "pitcher_name required")

    date_str = date.today().isoformat()
    if not use_token(email, pitcher_name, date_str):
        abort(402, "No tokens remaining — resets next Monday")

    full_pick = next((p for p in _store["picks"] if p["pitcher_name"] == pitcher_name), None)
    if not full_pick:
        abort(404, "Pick not found for today")

    token_info = get_token_info(email)
    return jsonify({
        "pick":             {**full_pick, "locked": False},
        "tokens_remaining": token_info["tokens_remaining"],
    })


@app.get("/api/picks/slate")
def todays_slate():
    """Returns raw probable starters without model predictions."""
    return jsonify({
        "date":    date.today().isoformat(),
        "starters": _store["slate"],
    })


@app.get("/api/performance")
def performance():
    if not _current_email():
        abort(401, "Sign in to view performance data")
    results_path = Path(__file__).parent / "backend" / "artifacts" / "backtest_results_combined.json"
    if not results_path.exists():
        results_path = Path(__file__).parent / "backend" / "artifacts" / "backtest_results.json"
    if not results_path.exists():
        return jsonify({"error": "No backtest results yet. Run: cd backend && python -m train.backtest"}), 404

    data = json.loads(results_path.read_text())

    # Merge in live resolved bets from prediction_log
    live_resolved = [
        r for r in get_live_record().get("records", [])
        if r.get("outcome") and (r.get("bet") or 0) > 0
    ]
    if live_resolved:
        overall = data["overall"]
        for r in live_resolved:
            overall["bets"]    += 1
            overall["wins"]    += 1 if r["outcome"] == "WIN"  else 0
            overall["losses"]  += 1 if r["outcome"] == "LOSS" else 0
            overall["pushes"]  += 1 if r["outcome"] == "PUSH" else 0
            overall["wagered"] = (overall.get("wagered") or 0) + (r.get("bet") or 0)
            overall["pnl"]     += (r.get("pnl") or 0)
        w, l = overall["wins"], overall["losses"]
        win_rate = w / (w + l) * 100 if (w + l) > 0 else 0
        roi      = overall["pnl"] / overall["wagered"] * 100 if overall.get("wagered") else 0
        overall["winRate"] = f"{win_rate:.1f}%"
        overall["roi"]     = f"{'+' if roi >= 0 else ''}{roi:.1f}%"

        # Extend cumulative P&L curve
        running = data["cumulative_pnl"][-1] if data["cumulative_pnl"] else 0
        for r in sorted(live_resolved, key=lambda x: x.get("date", "")):
            running += (r.get("pnl") or 0)
            data["cumulative_pnl"].append(round(running, 2))

        # Update / append monthly buckets
        monthly_map = {m["month"]: m for m in data["monthly"]}
        for r in live_resolved:
            key = (r.get("date") or "")[:7]
            if key not in monthly_map:
                monthly_map[key] = {"month": key, "bets": 0, "wins": 0, "losses": 0,
                                    "pushes": 0, "pnl": 0.0, "wagered": 0.0, "roi": 0.0}
            m = monthly_map[key]
            m["bets"]    += 1
            m["wins"]    += 1 if r["outcome"] == "WIN"  else 0
            m["losses"]  += 1 if r["outcome"] == "LOSS" else 0
            m["pushes"]  += 1 if r["outcome"] == "PUSH" else 0
            m["pnl"]     += (r.get("pnl") or 0)
            m["wagered"]  = m.get("wagered", 0) + (r.get("bet") or 0)
            if m.get("wagered"):
                m["roi"] = round(m["pnl"] / m["wagered"] * 100, 1)
        data["monthly"] = sorted(monthly_map.values(), key=lambda x: x["month"])

    # Recent bets for the current month (live first, then backtest fill)
    current_month = date.today().strftime("%Y-%m")
    all_records   = data.get("records", [])
    month_records = [
        r for r in all_records
        if (r.get("date") or "")[:7] == current_month and r.get("outcome")
    ]
    for r in live_resolved:
        if (r.get("date") or "")[:7] == current_month:
            month_records.append(r)
    month_records.sort(key=lambda r: r.get("date", ""), reverse=True)

    data["recent_bets"] = [
        {
            "date":           r.get("date", ""),
            "pitcher_name":   r.get("pitcher_name", ""),
            "recommendation": r.get("recommendation") or r.get("rec", ""),
            "line":           r.get("line"),
            "actual_ks":      r.get("actual") or r.get("actual_ks"),
            "outcome":        r.get("outcome", ""),
            "pnl":            round(r.get("pnl") or 0, 2),
            "bet":            round(r.get("bet") or 0, 2),
            "edge_pct":       r.get("edge_pct"),
        }
        for r in month_records[:20]
    ]

    return jsonify(data)


@app.get("/api/k-accuracy")
def k_accuracy():
    if _current_tier() != "premium":
        abort(403, "Premium required")

    artifacts = Path(__file__).parent / "backend" / "artifacts"

    # Full all-starters backtest (no lines needed — 6k+ games, 207 pitchers)
    seen = set()
    records = []
    acc_path = artifacts / "k_accuracy_backtest.json"
    if acc_path.exists():
        for r in json.loads(acc_path.read_text()).get("records", []):
            key = (r["pitcher_name"], r["date"])
            if key not in seen:
                seen.add(key)
                records.append({
                    "pitcher_name": r["pitcher_name"],
                    "predicted_ks": r["predicted_ks"],
                    "actual_ks":    r["actual_ks"],
                    "date":         r["date"],
                })

    # Live resolved bets appended as they settle
    for r in get_live_record().get("records", []):
        if r.get("actual_ks") is not None and (r.get("bet") or 0) > 0:
            key = (r["pitcher_name"], r["date"])
            if key not in seen:
                seen.add(key)
                records.append({
                    "pitcher_name": r["pitcher_name"],
                    "predicted_ks": r["predicted_ks"],
                    "actual_ks":    r["actual_ks"],
                    "date":         r["date"],
                })

    if records:
        errors    = [abs(r["predicted_ks"] - r["actual_ks"]) for r in records]
        mae       = round(sum(errors) / len(errors), 2)
        within_1  = round(sum(1 for e in errors if e <= 1) / len(errors) * 100, 1)
        within_2  = round(sum(1 for e in errors if e <= 2) / len(errors) * 100, 1)
    else:
        mae = within_1 = within_2 = None

    return jsonify({"records": records, "mae": mae, "within_1": within_1, "within_2": within_2})


@app.get("/api/live-record")
def live_record():
    _auto_resolve_pending()
    return jsonify(get_live_record())


def _auto_resolve_pending():
    """Fetch actual Ks for any pending taken bets or skipped entries from before today."""
    import urllib.request, json as _json
    today = date.today().isoformat()
    record = get_live_record()
    pending_taken   = [r for r in record.get("records", []) if r.get("outcome") is None and r.get("date", today) < today]
    pending_skipped = [r for r in get_skipped_record() if r.get("actual_ks") is None and r.get("date", today) < today]
    dates_to_check = sorted({r["date"] for r in pending_taken + pending_skipped})
    for date_str in dates_to_check:
        try:
            url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=boxscore"
            with urllib.request.urlopen(url, timeout=15) as r:
                data = _json.loads(r.read())
            results = []
            for date_entry in data.get("dates", []):
                for game in date_entry.get("games", []):
                    if game.get("status", {}).get("abstractGameState") != "Final":
                        continue
                    box_url = f"https://statsapi.mlb.com/api/v1/game/{game['gamePk']}/boxscore"
                    with urllib.request.urlopen(box_url, timeout=15) as br:
                        box = _json.loads(br.read())
                    for side in ("home", "away"):
                        team = box.get("teams", {}).get(side, {})
                        pitchers = team.get("pitchers", [])
                        players  = team.get("players", {})
                        if not pitchers:
                            continue
                        starter_id = pitchers[0]
                        stats = players.get(f"ID{starter_id}", {}).get("stats", {}).get("pitching", {})
                        ks = stats.get("strikeOuts")
                        if ks is not None:
                            results.append({"mlbam_id": starter_id, "actual_ks": float(ks)})
            if results:
                update_results(date_str, results)
                update_skipped_results(date_str, results)
                update_actuals(date_str, results)
                print(f"  [auto-resolve] {date_str}: resolved {len(results)} starters")
        except Exception as e:
            print(f"  [auto-resolve] {date_str} failed: {e}")


@app.get("/api/skipped")
def skipped_record():
    if _current_tier() != "premium":
        abort(403, "Premium required")
    _auto_resolve_pending()
    records = get_skipped_record()

    # Also include prediction_log entries where bet == 0 (Kelly sized out)
    from backend.app.data.prediction_log import get_live_record
    live = get_live_record().get("records", [])
    for r in live:
        if not r.get("bet"):
            merged = {
                "date":         r.get("date"),
                "pitcher_name": r.get("pitcher_name"),
                "mlbam_id":     r.get("mlbam_id"),
                "line":         r.get("line"),
                "predicted_ks": r.get("predicted_ks"),
                "actual_ks":    r.get("actual_ks"),
                "edge":         r.get("edge"),
                "confidence":   r.get("confidence"),
                "recommendation": r.get("recommendation"),
                "skip_reason":  "Kelly stake = $0",
            }
            records.append(merged)

    for r in records:
        if r.get("actual_ks") is not None:
            r["miss"] = round(r["actual_ks"] - r["predicted_ks"], 2)
        else:
            r["miss"] = None
    return jsonify(records)


@app.delete("/api/picks/log-lines")
def delete_log_line():
    if _current_tier() != "premium":
        abort(403, "Premium required")
    body = request.get_json(force=True)
    date_str     = body.get("date")
    pitcher_name = body.get("pitcher_name")
    if not date_str or not pitcher_name:
        abort(400, "Missing date or pitcher_name")
    deleted = delete_prediction(date_str, pitcher_name)
    return jsonify({"deleted": deleted})


@app.post("/api/picks/log-lines")
def log_lines():
    """
    Accept manually submitted lines and log predictions for today.
    Requires premium tier.

    Body: {"lines": [{"pitcher_name": "Gerrit Cole", "line": 6.5, "over_odds": -115}, ...]}
    """
    if _current_tier() != "premium":
        abort(403, "Premium required")
    if not _store["model_loaded"]:
        abort(503, "Model not loaded")

    body  = request.get_json(force=True)
    lines = body.get("lines", [])
    if not lines:
        abort(400, "No lines provided")

    season    = date.today().year
    game_date = date.today().isoformat()
    try:
        team_k = get_team_k_pct(season)
    except Exception:
        team_k = {}

    from backend.app.data.mlb_api import search_pitcher

    # Build a name→starter map from today's loaded slate for fast lookup
    slate_map = {_ascii(s["pitcher_name"]): s for s in _store.get("slate", [])}

    predictions = []
    skipped = []
    for entry in lines:
        name       = entry.get("pitcher_name", "").strip()
        line       = float(entry.get("line", 5.5))
        over_odds  = int(entry.get("over_odds", -115))
        under_odds = int(entry.get("under_odds", -115))
        book       = entry.get("book", "manual")

        if not name:
            continue

        try:
            # Try to find this pitcher in today's slate first (has opponent/park info)
            name_ascii = _ascii(name)
            slate_entry = slate_map.get(name_ascii)
            if not slate_entry:
                # Fuzzy match by last name (accent-insensitive)
                last = name_ascii.split()[-1]
                slate_entry = next((s for k, s in slate_map.items() if last in k), None)

            if slate_entry:
                mlbam_id = slate_entry["mlbam_id"]
                features = _build_features_from_starter(slate_entry, team_k, game_date)
            else:
                # Fall back to MLB API name search for MLBAM ID + pipeline
                matches = search_pitcher(name, season)
                mlbam_id = matches[0]["mlbam_id"] if matches else None
                features = _build_features_manual({
                    "pitcher_name": name,
                    "mlbam_id":     mlbam_id,
                })

            if slate_entry:
                matchup = f"vs {slate_entry.get('opponent_abbr','???')} @ {'home' if slate_entry.get('is_home') else 'away'}"
            else:
                matchup = "vs ??? @ ???"
            pred = strikeout_model.predict(
                feature_row  = features,
                line         = line,
                over_odds    = over_odds,
                under_odds   = under_odds,
                pitcher_name = name,
                matchup      = matchup,
            )

            if pred.recommendation == "PASS":
                skip_reason = f"PASS — {pred.confidence} conf, {abs(pred.edge_pct)*100:.1f}% edge (threshold not met)"
                print(f"  [log-lines] {name}: skipped — {skip_reason}")
            elif pred.confidence == "LOW":
                skip_reason = f"LOW confidence ({abs(pred.edge_pct)*100:.1f}% edge)"
            elif pred.recommendation == "UNDER" and abs(pred.edge_pct) < MIN_EDGE_UNDER:
                skip_reason = f"UNDER edge {abs(pred.edge_pct)*100:.1f}% < {MIN_EDGE_UNDER*100:.0f}% threshold"
            elif pred.recommendation == "OVER" and abs(pred.edge_pct) < MIN_EDGE_OVER:
                skip_reason = f"OVER edge {abs(pred.edge_pct)*100:.1f}% < {MIN_EDGE_OVER*100:.0f}% threshold"
                print(f"  [log-lines] {name}: skipped — {skip_reason}")
            else:
                skip_reason = None

            if skip_reason:
                skip_entry = {
                    "pitcher_name":    name,
                    "mlbam_id":        mlbam_id or 0,
                    "line":            line,
                    "over_odds":       over_odds,
                    "under_odds":      under_odds,
                    "predicted_ks":    pred.predicted_ks,
                    "recommendation":  pred.recommendation,
                    "edge":            round(pred.edge_pct, 4),
                    "confidence":      pred.confidence,
                    "model_prob_over": pred.model_prob_over,
                    "skip_reason":     skip_reason,
                }
                skipped.append(skip_entry)
                continue

            # Use correct side's odds for Kelly sizing
            if pred.recommendation == "OVER":
                model_prob_win = pred.model_prob_over
                bet_odds = over_odds
            else:
                model_prob_win = 1 - pred.model_prob_over
                bet_odds = under_odds
            bet = _kelly_bet(model_prob_win, bet_odds)

            fv = pred.features_used
            predictions.append({
                "pitcher_name":    name,
                "mlbam_id":        mlbam_id or 0,
                "line":            line,
                "over_odds":       over_odds,
                "under_odds":      under_odds,
                "bet_odds":        bet_odds,
                "line_source":     book,
                "predicted_ks":    pred.predicted_ks,
                "recommendation":  pred.recommendation,
                "edge":            round(pred.edge_pct, 4),
                "confidence":      pred.confidence,
                "model_prob_over": pred.model_prob_over,
                "bet":             bet,
                "features": {
                    "k5":            _safe(fv.get("k_pct_last5")),
                    "k15":           _safe(fv.get("k_pct_last15")),
                    "ks":            _safe(fv.get("k_pct_season")),
                    "fip":           _safe(fv.get("fip_last15")),
                    "ip5":           _safe(fv.get("avg_ip_last5")),
                    "ff":            _safe(fv.get("ff_pct")),
                    "velo":          _safe(fv.get("ff_velo_avg")),
                    "spin":          _safe(fv.get("ff_spin_avg")),
                    "swstr":         _safe(fv.get("swstr_pct")),
                    "whiff":         _safe(fv.get("whiff_pct")),
                    "csw":           _safe(fv.get("csw_pct")),
                    "opp":           _safe(fv.get("opp_k_pct"), 0.225),
                    "lineup_opp":    _safe(fv.get("opp_lineup_k_pct")),
                    "matchup_score": _safe(fv.get("matchup_k_score")),
                    "umpire":        _safe(fv.get("umpire_k_rate")),
                },
            })
        except Exception as e:
            print(f"  [log-lines] {name}: {e}")

    count = log_predictions(predictions)
    log_skipped(skipped)
    return jsonify({"logged": count, "predictions": predictions, "skipped": skipped})


@app.get("/api/debug/odds")
def debug_odds():
    """Dump raw DraftKings API response so we can see the real field structure."""
    from backend.app.data.odds_api import _get, MLB_GROUP
    try:
        # Step 1: top-level event group — look for category structure
        top = _get(f"/eventgroups/{MLB_GROUP}", {"format": "json"})
        eg  = top.get("eventGroup", {})

        cats = eg.get("offerCategories", [])
        cat_summary = []
        for c in cats:
            subs = c.get("offerSubcategoryDescriptors", [])
            cat_summary.append({
                "offerCategoryId": c.get("offerCategoryId"),
                "name":            c.get("name"),
                "subcategories": [
                    {"subcategoryId": s.get("subcategoryId"), "name": s.get("name")}
                    for s in subs
                ],
            })

        return jsonify({
            "eventGroupName": eg.get("name"),
            "totalCategories": len(cats),
            "categories": cat_summary,
            "top_level_keys": list(eg.keys()),
        })
    except Exception as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


@app.post("/api/picks/predict")
def predict():
    if _current_tier() != "premium":
        abort(403, "Premium required")
    if not _store["model_loaded"]:
        abort(503, "Model not loaded")

    body = request.get_json(force=True)
    for field in ["pitcher_name", "park_team", "line"]:
        if field not in body:
            abort(400, f"Missing field: {field}")

    try:
        features = _build_features_manual(body)
        matchup  = f"vs {body.get('opponent_team','OPP')} @ {'home' if body.get('is_home') else 'away'}"
        pred = strikeout_model.predict(
            feature_row = features,
            line        = float(body["line"]),
            over_odds   = int(body.get("over_odds", -115)),
            pitcher_name= body["pitcher_name"],
            matchup     = matchup,
        )
        return jsonify({
            "pitcher_name":      pred.pitcher_name,
            "matchup":           pred.matchup,
            "predicted_ks":      pred.predicted_ks,
            "line":              pred.line,
            "model_prob_over":   pred.model_prob_over,
            "implied_prob_over": pred.implied_prob_over,
            "edge_pct":          pred.edge_pct,
            "edge_pct_display":  _format_edge(pred.edge_pct),
            "confidence":        pred.confidence,
            "recommendation":    pred.recommendation,
        })
    except Exception as e:
        abort(422, str(e))


@app.post("/api/picks/refresh")
def force_refresh():
    # force_odds_refresh=True so a manual refresh always pulls fresh lines from the API
    threading.Thread(target=refresh_data, kwargs={"force_odds_refresh": True}, daemon=True).start()
    return jsonify({"status": "refresh started"})


def _run_hitting_refresh():
    """Re-run hitting pipeline with fresh lines — called from /api/hitting/refresh thread."""
    invalidate_schedule_cache()
    game_date = date.today().isoformat()
    try:
        live_h_slate = build_live_hitting_slate(game_date, force_refresh=True) or []
    except Exception as e:
        print(f"[hitting_refresh] pipeline error: {e}")
        live_h_slate = []
    try:
        h_picks, h_all = _run_hitting_slate(live_h_slate)
    except Exception as e:
        print(f"[hitting_refresh] _run_hitting_slate error: {e}")
        h_picks, h_all = [], []
    _hitting_store["picks"]         = h_picks
    _hitting_store["all_processed"] = h_all
    _hitting_store["last_update"]   = datetime.now().isoformat(timespec="seconds")
    print(f"[hitting_refresh] {len(h_picks)} hitting picks ready ({len(live_h_slate)} slate rows).")


@app.post("/api/hitting/refresh")
def hitting_force_refresh():
    if not _current_email():
        abort(401)
    threading.Thread(target=_run_hitting_refresh, daemon=True).start()
    return jsonify({"status": "refresh started"})


# ---------------------------------------------------------------------------
# Hitting API routes
# ---------------------------------------------------------------------------

HITTING_MODEL_VERSION = "hitting-xgb-v1"


@app.get("/api/hitting/today")
def hitting_today():
    email    = _current_email()
    tier     = get_tier(email) if email else "free"
    edge_picks = _hitting_store["picks"]
    all_processed = _hitting_store["all_processed"]
    date_str  = date.today().isoformat()

    if tier == "premium":
        # Show all processed batters (edge picks first, then PASS picks)
        edge_names = {p["batter_name"] for p in edge_picks}
        pass_picks = [p for p in all_processed if p["batter_name"] not in edge_names]
        all_picks = edge_picks + pass_picks
        return jsonify({
            "date":          date_str,
            "picks":         all_picks,
            "total_picks":   len(edge_picks),
            "tier":          "premium",
            "model_version": HITTING_MODEL_VERSION,
            "last_update":   _hitting_store["last_update"],
        })

    # Free tier — show top 2 edge picks, lock the rest
    all_picks = edge_picks
    unlocked   = get_unlocked_today(email, date_str) if email else []
    token_info = get_token_info(email) if email else {"tokens_remaining": 0, "tokens_reset_at": None}

    picks_out = []
    for i, pick in enumerate(all_picks):
        if pick["batter_name"] in unlocked or i < FREE_PICKS_LIMIT:
            picks_out.append({**pick, "locked": False})
        else:
            picks_out.append({
                "batter_name": pick["batter_name"],
                "matchup":     pick.get("matchup", ""),
                "team":        pick.get("team", ""),
                "opponent":    pick.get("opponent", ""),
                "has_line":    pick.get("has_line", True),
                "locked":      True,
            })

    return jsonify({
        "date":             date_str,
        "picks":            picks_out,
        "total_picks":      len(all_picks),
        "tier":             "free",
        "tokens_remaining": token_info["tokens_remaining"],
        "tokens_reset_at":  token_info["tokens_reset_at"],
        "model_version":    HITTING_MODEL_VERSION,
        "last_update":      _hitting_store["last_update"],
    })


@app.get("/api/hitting/performance")
def hitting_performance():
    if not _current_email():
        abort(401, "Sign in to view performance data")

    # Optional model summary — compact JSON without records array
    _summary_candidates = [
        Path(__file__).parent / "backend" / "artifacts" / "hitting_backtest_summary.json",
        Path(__file__).parent / "backend" / "artifacts" / "hitting_backtest.json",
    ]
    bt = None
    for p in _summary_candidates:
        if p.exists():
            try:
                bt = json.loads(p.read_text())
            except Exception:
                pass
            break

    # Live bet performance from hitting_prediction_log
    live_rec      = get_hitting_live_record()
    live_resolved = [r for r in live_rec.get("records", []) if r.get("outcome") and (r.get("bet") or 0) > 0]

    wins   = sum(1 for r in live_resolved if r["outcome"] == "WIN")
    losses = sum(1 for r in live_resolved if r["outcome"] == "LOSS")
    pushes = sum(1 for r in live_resolved if r["outcome"] == "PUSH")
    total_wagered = sum(r.get("bet", 0) or 0 for r in live_resolved)
    total_pnl     = sum(r.get("pnl", 0) or 0 for r in live_resolved)
    roi      = (total_pnl / total_wagered * 100) if total_wagered > 0 else 0
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    # Cumulative P&L curve
    cumulative_pnl = []
    running = 0
    for r in sorted(live_resolved, key=lambda x: x.get("date", "")):
        running += r.get("pnl") or 0
        cumulative_pnl.append(round(running, 2))

    # Monthly buckets from live bets
    monthly_map: dict = {}
    for r in live_resolved:
        key = (r.get("date") or "")[:7]
        if key not in monthly_map:
            monthly_map[key] = {"month": key, "bets": 0, "wins": 0, "losses": 0,
                                "pushes": 0, "pnl": 0.0, "wagered": 0.0, "roi": 0.0}
        m = monthly_map[key]
        m["bets"]    += 1
        m["wins"]    += 1 if r["outcome"] == "WIN"  else 0
        m["losses"]  += 1 if r["outcome"] == "LOSS" else 0
        m["pushes"]  += 1 if r["outcome"] == "PUSH" else 0
        m["pnl"]     += r.get("pnl") or 0
        m["wagered"]  = m.get("wagered", 0) + (r.get("bet") or 0)
        if m.get("wagered"):
            m["roi"] = round(m["pnl"] / m["wagered"] * 100, 1)
    monthly = sorted(monthly_map.values(), key=lambda x: x["month"])

    # Confidence breakdown from live bets
    byTier: dict = {}
    for r in live_resolved:
        tier = r.get("confidence", "LOW") or "LOW"
        if tier not in byTier:
            byTier[tier] = {"bets": 0, "wins": 0, "losses": 0, "pushes": 0, "pnl": 0.0, "wagered": 0.0}
        byTier[tier]["bets"]   += 1
        byTier[tier]["wins"]   += 1 if r["outcome"] == "WIN"  else 0
        byTier[tier]["losses"] += 1 if r["outcome"] == "LOSS" else 0
        byTier[tier]["pushes"] += 1 if r["outcome"] == "PUSH" else 0
        byTier[tier]["pnl"]    += r.get("pnl") or 0
        byTier[tier]["wagered"] += r.get("bet") or 0
    for tier, stats in byTier.items():
        denom    = stats["wins"] + stats["losses"]
        wr       = (stats["wins"] / denom * 100) if denom > 0 else 0
        roi_tier = (stats["pnl"] / stats["wagered"] * 100) if stats["wagered"] > 0 else 0
        stats["winRate"] = f"{wr:.1f}%"
        stats["roi"]     = f"{'+' if roi_tier >= 0 else ''}{roi_tier:.1f}%"

    current_month = date.today().strftime("%Y-%m")
    recent_bets = [
        {
            "date":           r.get("date", ""),
            "batter_name":    r.get("batter_name", ""),
            "recommendation": r.get("recommendation") or r.get("rec", ""),
            "line":           r.get("line"),
            "actual_hits":    r.get("actual_hits"),
            "outcome":        r.get("outcome", ""),
            "pnl":            round(r.get("pnl") or 0, 2),
            "bet":            round(r.get("bet") or 0, 2),
            "edge_pct":       r.get("edge"),
        }
        for r in sorted(live_resolved, key=lambda x: x.get("date", ""), reverse=True)
        if (r.get("date") or "")[:7] == current_month
    ][:20]

    # Include model accuracy quick-stats from summary if available
    model_accuracy = None
    if bt:
        model_accuracy = {
            "mae":         bt.get("overall", {}).get("mae"),
            "within_half": round(bt.get("error_distribution", {}).get("within_0.50", 0) * 100, 1),
            "within_one":  round(bt.get("error_distribution", {}).get("within_1.00", 0) * 100, 1),
            "test_rows":   bt.get("test_rows"),
        }

    return jsonify({
        "overall": {
            "bets":    len(live_resolved),
            "wins":    wins,
            "losses":  losses,
            "pushes":  pushes,
            "winRate": f"{win_rate:.1f}%",
            "roi":     f"{'+' if roi >= 0 else ''}{roi:.1f}%",
            "pnl":     round(total_pnl, 2),
            "wagered": round(total_wagered, 2),
        },
        "byTier":         byTier,
        "monthly":        monthly,
        "cumulative_pnl": cumulative_pnl,
        "bankroll":       1000,
        "kelly_frac":     0.25,
        "recent_bets":    recent_bets,
        "model_accuracy": model_accuracy,
    })


@app.get("/api/hitting/live-record")
def hitting_live_record():
    _auto_resolve_hitting_pending()
    return jsonify(get_hitting_live_record())


def _auto_resolve_hitting_pending():
    """Fetch actual hits for pending batter picks from before today."""
    import urllib.request, json as _json
    today = date.today().isoformat()
    record = get_hitting_live_record()
    pending = [r for r in record.get("records", []) if r.get("outcome") is None and r.get("date", today) < today]
    dates_to_check = sorted({r["date"] for r in pending})
    for date_str in dates_to_check:
        try:
            url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=boxscore"
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = _json.loads(resp.read())
            results = []
            for date_entry in data.get("dates", []):
                for game in date_entry.get("games", []):
                    if game.get("status", {}).get("abstractGameState") != "Final":
                        continue
                    box_url = f"https://statsapi.mlb.com/api/v1/game/{game['gamePk']}/boxscore"
                    with urllib.request.urlopen(box_url, timeout=15) as br:
                        box = _json.loads(br.read())
                    for side in ("home", "away"):
                        team    = box.get("teams", {}).get(side, {})
                        players = team.get("players", {})
                        for pid, pdata in players.items():
                            batter_id = pdata.get("person", {}).get("id")
                            hits = pdata.get("stats", {}).get("batting", {}).get("hits")
                            if batter_id and hits is not None:
                                results.append({"mlbam_id": batter_id, "actual_hits": float(hits)})
            if results:
                update_hitting_results(date_str, results)
                update_hitting_skipped_results(date_str, results)
                print(f"  [hitting-resolve] {date_str}: resolved {len(results)} batters")
        except Exception as e:
            print(f"  [hitting-resolve] {date_str} failed: {e}")


@app.get("/api/hitting/skipped")
def hitting_skipped():
    if _current_tier() != "premium":
        abort(403, "Premium required")
    _auto_resolve_hitting_pending()
    records = get_hitting_skipped_record()
    live = get_hitting_live_record().get("records", [])
    for r in live:
        if not r.get("bet"):
            records.append({
                "date":         r.get("date"),
                "batter_name":  r.get("batter_name"),
                "mlbam_id":     r.get("mlbam_id"),
                "line":         r.get("line"),
                "predicted_hits": r.get("predicted_hits"),
                "actual_hits":  r.get("actual_hits"),
                "edge":         r.get("edge"),
                "confidence":   r.get("confidence"),
                "recommendation": r.get("recommendation"),
                "skip_reason":  "Kelly stake = $0",
                "miss":         None,
            })
    for r in records:
        if r.get("actual_hits") is not None and r.get("predicted_hits") is not None:
            r["miss"] = round(r["actual_hits"] - r["predicted_hits"], 2)
    return jsonify(records)


@app.get("/api/hitting/debug")
def hitting_debug():
    """
    Probe the Odds API to see exactly what batter hit lines are available.
    Checks events, available markets on one sample event, and credit usage.
    Only fetches odds for the FIRST event to keep credit cost minimal (~2 credits total).
    """
    if not _current_email():
        abort(401)

    from backend.app.data.odds_api import _get as _odds_get, get_credits_remaining, invalidate_player_prop_cache
    invalidate_player_prop_cache()  # always fetch fresh for debug

    SPORT   = "baseball_mlb"
    REGIONS = "us"
    FMT     = "american"
    result  = {"events": [], "sample_markets": {}, "batter_hits_sample": [], "credits_remaining": None}

    try:
        events = _odds_get(f"/sports/{SPORT}/events", {"regions": REGIONS})
        result["events"] = [
            {"id": e.get("id"), "home": e.get("home_team"), "away": e.get("away_team"),
             "commence": e.get("commence_time")}
            for e in (events if isinstance(events, list) else [])
        ]
        result["event_count"] = len(result["events"])
    except Exception as exc:
        result["events_error"] = str(exc)
        result["credits_remaining"] = get_credits_remaining()
        return jsonify(result)

    # Probe only the first event to minimise credit burn
    if result["events"]:
        first_id = result["events"][0]["id"]

        # Try batter_hits market
        try:
            odds = _odds_get(f"/sports/{SPORT}/events/{first_id}/odds",
                             {"regions": REGIONS, "markets": "batter_hits", "oddsFormat": FMT})
            bookmakers = odds.get("bookmakers", [])
            result["sample_markets"]["batter_hits"] = {
                "bookmaker_count": len(bookmakers),
                "bookmakers": [b.get("title") for b in bookmakers],
                "outcome_count": sum(
                    len(m.get("outcomes", []))
                    for b in bookmakers for m in b.get("markets", [])
                    if m.get("key") == "batter_hits"
                ),
            }
            # Pull first 5 player names as a sample
            names = []
            for bm in bookmakers:
                for mkt in bm.get("markets", []):
                    if mkt.get("key") == "batter_hits":
                        for o in mkt.get("outcomes", []):
                            desc = o.get("description") or o.get("name", "")
                            if desc and desc not in names:
                                names.append(desc)
            result["batter_hits_sample"] = names[:10]
        except Exception as exc:
            result["sample_markets"]["batter_hits_error"] = str(exc)

        # Also try alternate market key spellings DK might use
        for alt_key in ("player_hits", "batter_hits_alternate", "batter_total_hits"):
            try:
                odds2 = _odds_get(f"/sports/{SPORT}/events/{first_id}/odds",
                                  {"regions": REGIONS, "markets": alt_key, "oddsFormat": FMT})
                bms = odds2.get("bookmakers", [])
                if bms:
                    result["sample_markets"][alt_key] = {
                        "bookmaker_count": len(bms),
                        "outcome_count": sum(
                            len(m.get("outcomes", []))
                            for b in bms for m in b.get("markets", [])
                            if m.get("key") == alt_key
                        ),
                    }
            except Exception:
                pass

    result["credits_remaining"] = get_credits_remaining()
    return jsonify(result)


@app.get("/api/hitting/accuracy")
def hitting_accuracy():
    if _current_tier() != "premium":
        abort(403, "Premium required")
    _candidates = [
        Path(__file__).parent / "backend" / "artifacts" / "hitting_backtest_summary.json",
        Path(__file__).parent / "backend" / "artifacts" / "hitting_backtest.json",
    ]
    bt = None
    for p in _candidates:
        if p.exists():
            try:
                bt = json.loads(p.read_text())
            except Exception:
                pass
            break
    if bt is None:
        return jsonify({"mae": None, "within_half": None, "within_one": None,
                        "by_month": [], "by_line": {}, "by_confidence": {}, "test_rows": None})
    return jsonify({
        "mae":           bt.get("overall", {}).get("mae"),
        "within_half":   round(bt.get("error_distribution", {}).get("within_0.50", 0) * 100, 1),
        "within_one":    round(bt.get("error_distribution", {}).get("within_1.00", 0) * 100, 1),
        "by_month":      bt.get("by_month", []),
        "by_line":       bt.get("by_line", {}),
        "by_confidence": bt.get("by_confidence", {}),
        "test_rows":     bt.get("test_rows"),
    })


@app.delete("/api/hitting/log-lines")
def delete_hitting_log_line():
    if _current_tier() != "premium":
        abort(403, "Premium required")
    body = request.get_json(force=True)
    date_str    = body.get("date")
    batter_name = body.get("batter_name")
    if not date_str or not batter_name:
        abort(400, "Missing date or batter_name")
    deleted = delete_hitting_prediction(date_str, batter_name)
    return jsonify({"deleted": deleted})


# ---------------------------------------------------------------------------
# Serve React frontend
# ---------------------------------------------------------------------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    dist = FRONTEND_DIST
    if not dist.exists():
        return (
            "<h2 style='font-family:monospace;padding:2rem'>Frontend not built yet.</h2>"
            "<p style='font-family:monospace;padding:0 2rem'>Run: <code>cd frontend && npm run build</code></p>",
            200,
        )
    target = dist / path
    if path and target.exists():
        return send_from_directory(dist, path)
    return send_from_directory(dist, "index.html")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()

    def _startup_refresh():
        time.sleep(15)  # let Flask bind and pass the health check first
        try:
            refresh_data()
        except Exception as e:
            print(f"[startup] refresh_data error: {e}")

    threading.Thread(target=_startup_refresh, daemon=True).start()
    threading.Thread(target=_background_maintenance, args=(3600,), daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    print(f"\n[mlbet] Running at http://0.0.0.0:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

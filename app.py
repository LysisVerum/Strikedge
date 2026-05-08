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
from backend.app.data.mlb_api import (
    get_todays_starters,
    get_team_k_pct,
    get_pitcher_multi_season_log,
    get_team_id_map,
    _ascii,
)
from backend.app.data.statcast_agg import get_pitcher_statcast_range, pitch_mix_features, invalidate_current_month
from backend.app.data.pipeline import build_inference_row
from backend.app.data.odds_api import get_sp_strikeout_lines, match_line_to_starter, get_credits_remaining
from backend.app.data.umpire import get_todays_umpires
from backend.app.data.prediction_log import (
    log_predictions, get_live_record, update_results, delete_prediction,
    log_skipped, update_skipped_results, get_skipped_record,
)
from backend.app.data.k_log import log_slate_predictions, update_actuals, get_accuracy_stats
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
    "picks":        [],
    "slate":        [],   # raw starters from MLB API
    "last_update":  None,
    "model_loaded": False,
    "refresh_running": False,
}
_refresh_lock = threading.Lock()


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
    return meaningful


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
        print(f"[mlbet] {len(starters)} probable starters found.")
    except Exception as e:
        print(f"[mlbet] Could not fetch starters: {e}")
        starters = []

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

    print("[mlbet] Fetching live strikeout lines...")
    try:
        live_lines = get_sp_strikeout_lines(force_refresh=force_odds_refresh)
        print(f"[mlbet] {len(live_lines)} live lines loaded.")
    except Exception as e:
        print(f"[mlbet] Could not fetch live lines: {e} — using model lines")
        live_lines = {}

    print("[mlbet] Fetching today's umpires...")
    try:
        umpire_map = get_todays_umpires(game_date)
        print(f"[mlbet] {len(umpire_map)} umpires fetched.")
    except Exception as e:
        print(f"[mlbet] Could not fetch umpires: {e}")
        umpire_map = {}

    print("[mlbet] Building feature rows and running model...")
    try:
        picks = _run_slate(starters, team_k_map, game_date, live_lines, umpire_map)
    except Exception as e:
        print(f"[mlbet] _run_slate error: {e}")
        picks = []

    _store["picks"]       = picks
    _store["slate"]       = starters
    _store["last_update"] = datetime.now().isoformat(timespec="seconds")
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
        return jsonify({
            "date":          date_str,
            "picks":         all_picks,
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

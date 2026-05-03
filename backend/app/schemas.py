from pydantic import BaseModel, Field
from typing import Literal


class PredictRequest(BaseModel):
    pitcher_name: str = Field(..., example="Gerrit Cole")
    last_name: str = Field(..., example="Cole")
    first_name: str = Field(..., example="Gerrit")
    opponent_team: str = Field(..., example="BOS")
    park_team: str = Field(..., description="Home team abbreviation (determines ballpark)", example="NYY")
    is_home: bool = Field(..., example=True)
    days_rest: int = Field(..., ge=1, le=10, example=5)
    line: float = Field(..., description="Sportsbook strikeout O/U line", example=7.5)
    over_odds: int = Field(default=-115, description="American odds for the over", example=-115)
    # Rolling stats — optionally provided; if missing, fetched from pybaseball
    k_pct_last5: float | None = Field(None, description="Override: K% over last 5 starts")
    k_pct_last15: float | None = Field(None, description="Override: K% over last 15 starts")
    k_pct_season: float | None = Field(None)
    avg_ip_last5: float | None = Field(None)
    opp_k_pct: float | None = Field(None, description="Opponent team K% (last 14 days)")


class PredictionResponse(BaseModel):
    pitcher_name: str
    matchup: str
    predicted_ks: float
    line: float
    model_prob_over: float
    implied_prob_over: float
    edge_pct: float
    edge_pct_display: str  # "+8.4%"
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    recommendation: Literal["OVER", "UNDER", "PASS"]
    features: dict | None = None


class PickItem(BaseModel):
    rank: int
    pitcher_name: str
    matchup: str
    bet: str           # "Over 7.5 K"
    predicted_ks: float
    line: float
    edge_pct_display: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    recommendation: Literal["OVER", "UNDER", "PASS"]
    model_prob_over: float
    implied_prob_over: float
    features: dict | None = None


class TodayPicksResponse(BaseModel):
    date: str
    picks: list[PickItem]
    model_version: str

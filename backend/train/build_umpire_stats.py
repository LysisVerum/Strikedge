"""
Build historical umpire K-rate stats from Statcast + MLB API boxscores.

Usage:
    cd backend
    python -m train.build_umpire_stats

Only needs to run once (or yearly to add a new season).
Results cached to artifacts/umpire_stats.json.
Runtime: ~20-40 min on first run (MLB API call per game, ~2400 games/season).
Subsequent runs are fast — skips already-fetched games.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.umpire import build_umpire_stats

if __name__ == "__main__":
    t0 = time.time()
    build_umpire_stats(seasons=[2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024])
    print(f"\nDone in {(time.time()-t0)/60:.1f} min")

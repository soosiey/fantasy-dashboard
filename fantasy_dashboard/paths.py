import os
from pathlib import Path

# Centralize filesystem locations shared by multiple pages.
PROJECT_ROOT = Path(__file__).parents[1]
DATA_DIR = Path(
    os.environ.get("FANTASY_DASHBOARD_DATA_DIR", PROJECT_ROOT / "data")
).expanduser()
SNAPSHOT_STORAGE_DIR = DATA_DIR
SNAPSHOT_DATABASE_PATH = DATA_DIR / "fantasy_dashboard.sqlite3"
NFL_PLAYERS_PATH = DATA_DIR / "nfl_players.json"
ESPN_PROJECTIONS_CACHE_DIR = DATA_DIR / "cache" / "espn_projections"
WEEKLY_STATS_CACHE_DIR = DATA_DIR / "cache" / "weekly_stats"
DRAFT_ANALYSIS_CACHE_DIR = DATA_DIR / "cache" / "draft_analysis"
REGRESSION_CACHE_DIR = DATA_DIR / "cache" / "regression"
MANUAL_REFRESH_STATE_PATH = DATA_DIR / "cache" / "manual_refresh.json"

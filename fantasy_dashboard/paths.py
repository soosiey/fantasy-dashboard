from pathlib import Path

# Centralize filesystem locations shared by multiple pages.
PROJECT_ROOT = Path(__file__).parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SNAPSHOT_STORAGE_DIR = DATA_DIR
NFL_PLAYERS_PATH = DATA_DIR / "nfl_players.json"
ESPN_PROJECTIONS_CACHE_DIR = DATA_DIR / "cache" / "espn_projections"
WEEKLY_STATS_CACHE_DIR = DATA_DIR / "cache" / "weekly_stats"
DRAFT_ANALYSIS_CACHE_DIR = DATA_DIR / "cache" / "draft_analysis"
MANUAL_REFRESH_STATE_PATH = DATA_DIR / "cache" / "manual_refresh.json"

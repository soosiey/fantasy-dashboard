from pathlib import Path

# Centralize filesystem locations shared by multiple pages.
PROJECT_ROOT = Path(__file__).parents[1]
NFL_PLAYERS_PATH = PROJECT_ROOT / "nfl_players.json"

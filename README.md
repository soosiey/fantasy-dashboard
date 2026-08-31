# fantasy-dashboard
Fantasy fooball dashboard for sleeper. WIP


# Installation
Run

```bash
pip install -r requirements.txt
```

in a Python environment. For local development and tests, install the development
requirements instead:

```bash
pip install -r requirements-dev.txt
```

# Running
Run

```bash
streamlit run app.py
```

from the root directory.

## Application URLs

The application uses explicit, stable routes:

- `/leagues`
- `/overview?league_id=LEAGUE_ID`
- `/draft-results?league_id=LEAGUE_ID`
- `/transactions?league_id=LEAGUE_ID`
- `/players?league_id=LEAGUE_ID`
- `/matchups?league_id=LEAGUE_ID`
- `/rankings?league_id=LEAGUE_ID`
- `/team?league_id=LEAGUE_ID&user_id=USER_ID`

Matchup week/stat source and player-page filters are also stored in the URL.
Protected deep links return to their requested page after Sleeper login. The
former `/ranking` and `/draft_results` routes remain available as redirects.

Player projections are retrieved from ESPN and cached under
`data/cache/espn_projections/`. The raw ESPN response is reused for six hours
outside live games and one hour during live games. Sleeper's shared NFL player
catalog is stored at `data/nfl_players.json`.

## Manual historical snapshots

The snapshot collector preserves original provider responses as JSON and writes
normalized league, roster, matchup, schedule, scoring, projection, and actual
stat records to `data/fantasy_dashboard.sqlite3`. ESPN schedule snapshots supply
exact UTC kickoff timestamps, and every player statistic is linked to its NFL
team and game while player identity is versioned for that capture.

Capture projections and league context before games begin:

```bash
python take_snapshot.py pre-kickoff --league-id LEAGUE_ID --week 1
```

Capture actual statistics and final league context after the week:

```bash
python take_snapshot.py post-week --league-id LEAGUE_ID --week 1
```

The season and season type default to the selected league. Use `--season`,
`--season-type`, or `--storage-dir` to override them. Repeated pre-kickoff runs
are retained so analysis can later select the final capture before each game's
stored kickoff time.

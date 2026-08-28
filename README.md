# fantasy-dashboard
Fantasy fooball dashboard for sleeper. WIP


# Installation
Run

```pip install -r requirements.txt```

in a python environment. 

# Running
Run

```streamlit run app.py```

from the root directory.

Player projections are retrieved from ESPN and cached for one hour in memory
and under `data/cache/espn_projections/`. Sleeper's shared NFL player catalog is
stored at `data/nfl_players.json`.

## Manual historical snapshots

The snapshot collector preserves original provider responses as JSON and writes
normalized league, roster, matchup, schedule, scoring, projection, and actual
stat records to `data/fantasy_dashboard.sqlite3`.

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

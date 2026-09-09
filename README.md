# Fantasy Football Dashboard

A Streamlit dashboard for exploring Sleeper fantasy-football leagues, player
performance, matchups, draft quality, trades, and season projections.

Current application version: **1.1**

## Features

- Authenticate with a Sleeper username and select any associated league.
- Review rosters, standings, matchups, transactions, drafts, and playoff brackets.
- Compare actual and projected player performance under the league's scoring rules.
- Explore consistency, opportunity, efficiency, availability, trends, and projection
  accuracy.
- Compare players and inspect recent NBC Sports/Rotoworld news.
- Grade individual draft picks using positional strength, roster value, tier-drop
  cost, and auction-cost efficiency.
- Simulate the strength of the originally drafted teams and project the current
  regular season and playoff tournament.
- Evaluate player-only trades without submitting changes to Sleeper.
- Display a global **Game Active** indicator. Its light is green while a current-week
  NFL game is live and gray otherwise.

The dashboard is read-only. It does not submit lineups, transactions, trades, or
other changes to provider accounts.

## Production documentation

The detailed production baseline is maintained in the
[1.0 Release reference in Notion](https://app.notion.com/p/3d6c7de02bd281cd8e52d45d957642ab).
It contains:

- [Application State Diagram](https://app.notion.com/p/3d6c7de02bd2815f992adb34240be7d7)
- [Python File Inventory](https://app.notion.com/p/3d6c7de02bd2817b923df03729287f9d)
- [Mathematical & Inference Reference](https://app.notion.com/p/3d6c7de02bd281e1959ecf5dc74d16c2)
- [Caching & Refresh Reference](https://app.notion.com/p/3d6c7de02bd281e9997ae8b0c34d8fdd)
- [Data Sources & Endpoints](https://app.notion.com/p/3d6c7de02bd281a5b8d3d78d81161194)

The Notion pages document the 1.0 production baseline. Version 1.1 additionally
introduces the global live-game indicator and persistent completed-draft analysis
caches.

## Requirements

- Python 3.12 is recommended.
- Internet access to the Sleeper, ESPN, and NBC Sports endpoints.
- A Sleeper username for application login.
- A writable `data/` directory for JSON caches and historical snapshots.

The application does not require provider API keys or a secrets file.

## Run locally

From the repository root, create and activate a virtual environment.

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the runtime dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Start the dashboard:

```bash
python -m streamlit run app.py
```

Streamlit will print the local URL, normally
[http://localhost:8501](http://localhost:8501). Enter a Sleeper username, choose a
season and league, and the dashboard will open the league overview.

On the first run, the application may take longer while it downloads the Sleeper
player catalog and creates projection/stat caches. Later runs reuse those files.

## Development and tests

Install the development dependencies instead of the runtime-only set:

```bash
python -m pip install -r requirements-dev.txt
```

Run the test suite and lint checks:

```bash
python -m pytest
python -m ruff check .
```

The Streamlit smoke tests use deterministic offline providers, so the test suite
does not require a live Sleeper account.

## Application URLs

The application uses stable routes, including:

- `/leagues`
- `/overview?league_id=LEAGUE_ID`
- `/draft-results?league_id=LEAGUE_ID`
- `/transactions?league_id=LEAGUE_ID`
- `/players?league_id=LEAGUE_ID`
- `/matchups?league_id=LEAGUE_ID`
- `/rankings?league_id=LEAGUE_ID`
- `/analysis?league_id=LEAGUE_ID`
- `/comparison?league_id=LEAGUE_ID`
- `/league-predictions?league_id=LEAGUE_ID`
- `/regression?league_id=LEAGUE_ID`
- `/trade-analysis?league_id=LEAGUE_ID`
- `/team?league_id=LEAGUE_ID&user_id=USER_ID`

Protected deep links return to their requested page after Sleeper login. Matchup,
player, and analysis filters are also synchronized with URL query parameters where
applicable. The former `/ranking` and `/draft_results` routes remain available as
compatibility redirects.

## Data sources and caching

- **Sleeper** supplies users, leagues, rosters, matchups, drafts, transactions,
  brackets, schedules, actual statistics, trends, avatars, and the NFL player
  catalog.
- **ESPN Fantasy** supplies season and weekly player projections.
- **ESPN Site API** supplies exact NFL event timing for historical snapshots.
- **NBC Sports/Rotoworld** supplies recent player-news metadata and source links.

Provider data is cached in `data/cache/`, and the Sleeper player catalog is stored
at `data/nfl_players.json`. Refresh intervals depend on the data type and game state;
actual statistics use a one-minute freshness window while a game is live.

Completed-draft analysis is persistent:

- Per-pick grades are calculated once per draft and weight configuration.
- The 5,000-season drafted-roster simulation is calculated once per draft.
- Stored results under `data/cache/draft_analysis/` are reused until missing,
  malformed, or incompatible with the cache schema.
- In-progress drafts bypass this persistent cache so incomplete results are not
  frozen.

See the
[Caching & Refresh Reference](https://app.notion.com/p/3d6c7de02bd281e9997ae8b0c34d8fdd)
for the complete refresh policy.

## Historical snapshots

The snapshot collector preserves original provider responses as JSON and writes
normalized league, roster, matchup, schedule, scoring, projection, and actual-stat
records to `data/fantasy_dashboard.sqlite3`.

Capture projections and league context before games begin:

```bash
python take_snapshot.py pre-kickoff --league-id LEAGUE_ID --week 1
```

Capture actual statistics and final league context after the week:

```bash
python take_snapshot.py post-week --league-id LEAGUE_ID --week 1
```

The season and season type default to the selected league. Use `--season`,
`--season-type`, or `--storage-dir` to override them. Run the following command for
the complete CLI reference:

```bash
python take_snapshot.py --help
```

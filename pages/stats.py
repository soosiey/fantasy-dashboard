from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.player_details import render_player_stats_table
from fantasy_dashboard.data import (
    get_current_nfl_season,
    get_data_update,
    get_league,
    get_nfl_players,
    get_nfl_schedule,
    get_player_weekly_stats,
    get_projected_player_stats,
)
from fantasy_dashboard.graph_stats import (
    build_actual_weekly_stat_rows,
    build_week_opponents,
)
from fantasy_dashboard.player_stats import build_player_stat_row
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    PLAYER_STATS_MODE_KEY,
    require_authentication,
    resolve_context_id,
    resolve_league_id,
    sync_query_params,
)

require_authentication("stats")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

player_id = resolve_context_id("player_id", "graph_player_id")
if player_id is None:
    st.warning("Select a player first.")
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.switch_page("pages/graphs.py", query_params={"league_id": league_id})

if not st.session_state.get(PLAYER_STATS_MODE_KEY):
    st.session_state[PLAYER_STATS_MODE_KEY] = True
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.rerun()

st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 115rem; }</style>",
    unsafe_allow_html=True,
)
st.title("Stats")

players = get_nfl_players()
player = players.get(player_id)
if player is None:
    st.warning("That player could not be found in the local player cache.")
else:
    player_name = (
        f"{player.get('first_name') or ''} {player.get('last_name') or ''}"
    ).strip()
    position = str(player.get("position") or "—")
    team = str(player.get("team") or "FA")
    number = player.get("number")
    st.header(player_name or player_id)
    player_details = [team, position]
    if number not in (None, ""):
        player_details.append(f"#{number}")
    st.caption(" · ".join(player_details))

    try:
        current_season = int(get_current_nfl_season())
    except (requests.RequestException, KeyError, TypeError, ValueError):
        today = datetime.now(ZoneInfo("America/New_York")).date()
        current_season = today.year if today.month >= 3 else today.year - 1
        st.warning("The current NFL season could not be detected from Sleeper.")

    season_options = [str(current_season - offset) for offset in range(3)]
    requested_season = str(st.query_params.get("year") or "")
    requested_stats_source = str(st.query_params.get("stats") or "actual").casefold()
    requested_relevant = str(st.query_params.get("relevant") or "").casefold() in {
        "1",
        "true",
        "yes",
    }
    control_prefix = f"stats-{league_id}-{player_id}"
    season_key = f"{control_prefix}-year"
    source_key = f"{control_prefix}-source"
    relevant_key = f"{control_prefix}-relevant"
    control_defaults = {
        season_key: (
            requested_season
            if requested_season in season_options
            else season_options[0]
        ),
        source_key: (
            "Predicted" if requested_stats_source == "predicted" else "Actual"
        ),
        relevant_key: requested_relevant,
    }
    for control_key, default_value in control_defaults.items():
        if control_key not in st.session_state:
            st.session_state[control_key] = default_value
    if st.session_state[season_key] not in season_options:
        st.session_state[season_key] = season_options[0]
    if st.session_state[source_key] not in {"Actual", "Predicted"}:
        st.session_state[source_key] = "Actual"

    year_column, source_column, relevant_column = st.columns(3)
    with year_column:
        selected_season = st.selectbox("Year", season_options, key=season_key)
    with source_column:
        stats_source = (
            st.segmented_control(
                "Stat type",
                ["Actual", "Predicted"],
                key=source_key,
                width="stretch",
            )
            or "Actual"
        )
    with relevant_column:
        relevant_only = st.toggle("Only Relevant Stats", key=relevant_key)

    sync_query_params(
        league_id=league_id,
        player_id=player_id,
        year=selected_season,
        stats=stats_source.casefold(),
        relevant="true" if relevant_only else None,
    )

    league = get_league(league_id)
    weekly_rows: list[dict] = []
    data_updates = []
    if stats_source == "Predicted":
        try:
            schedule = get_nfl_schedule(selected_season, "regular")
        except (requests.RequestException, TypeError, ValueError):
            schedule = []
        opponents_by_week = build_week_opponents(schedule, team)
        try:
            for week in range(1, 19):
                projected_stats = get_projected_player_stats(
                    selected_season,
                    week,
                ).get(player_id, {})
                row = build_player_stat_row(
                    projected_stats,
                    league.scoring_settings,
                    week,
                )
                row["Opponent"] = opponents_by_week.get(week, "—")
                weekly_rows.append(row)
                data_updates.append(
                    get_data_update("projected_player_stats", selected_season, week)
                )
        except (requests.RequestException, TypeError, ValueError):
            st.warning("ESPN projections could not be loaded.")
    else:
        try:
            weekly_stats = get_player_weekly_stats(
                player_id,
                selected_season,
                "regular",
            )
            weekly_rows = build_actual_weekly_stat_rows(
                weekly_stats,
                league.scoring_settings,
            )
            data_updates.append(
                get_data_update(
                    "player_weekly_stats",
                    player_id,
                    selected_season,
                    "regular",
                )
            )
        except (requests.RequestException, TypeError, ValueError):
            st.warning("Actual player statistics could not be loaded.")

    if weekly_rows:
        render_player_stats_table(
            pd.DataFrame(weekly_rows),
            position,
            relevant_only=relevant_only,
        )
    else:
        st.info("No statistics are available for this player and year.")

    render_data_disclaimer(*data_updates)

with st.bottom:
    back_to_analysis = st.button("Back to Analysis")

if back_to_analysis:
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.switch_page(
        "pages/graphs.py",
        query_params={"league_id": league_id},
    )

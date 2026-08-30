from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
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
    build_week_axis_labels,
)
from fantasy_dashboard.player_stats import (
    build_player_stat_row,
    get_relevant_stat_fields,
)
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    PLAYER_STATS_MODE_KEY,
    PLAYER_STATS_PENDING_KEY,
    require_authentication,
    resolve_context_id,
    resolve_league_id,
    sync_query_params,
)

require_authentication("graph")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

player_id = resolve_context_id("player_id", "graph_player_id")
st.session_state.pop(PLAYER_STATS_PENDING_KEY, None)
if player_id is None:
    st.warning("Select a player to graph first.")
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.switch_page("pages/graphs.py", query_params={"league_id": league_id})

if not st.session_state.get(PLAYER_STATS_MODE_KEY):
    st.session_state[PLAYER_STATS_MODE_KEY] = True
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.rerun()

st.title("Graph")
st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 95rem; }</style>",
    unsafe_allow_html=True,
)

players = get_nfl_players()
player = players.get(player_id)
if player is None:
    st.warning("That player could not be found in the local player cache.")
else:
    player_name = (
        f"{player.get('first_name') or ''} {player.get('last_name') or ''}"
    ).strip()
    st.header(player_name or player_id)
    st.caption(f"{player.get('position') or '—'} · {player.get('team') or 'FA'}")

    try:
        current_season = int(get_current_nfl_season())
    except (requests.RequestException, KeyError, TypeError, ValueError):
        today = datetime.now(ZoneInfo("America/New_York")).date()
        current_season = today.year if today.month >= 3 else today.year - 1
        st.warning("The current NFL season could not be detected from Sleeper.")

    season_options = [str(current_season - offset) for offset in range(3)]
    position = str(player.get("position") or "")
    relevant_stat_options = [label for label, _ in get_relevant_stat_fields(position)]
    requested_season = str(st.query_params.get("year") or "")
    requested_stat = str(st.query_params.get("stat") or "")
    control_prefix = f"graph-{league_id}-{player_id}"
    season_key = f"{control_prefix}-year"
    stat_key = f"{control_prefix}-stat"
    control_defaults = {
        season_key: (
            requested_season
            if requested_season in season_options
            else season_options[0]
        ),
        stat_key: (
            requested_stat
            if requested_stat in relevant_stat_options
            else "Fantasy Points"
        ),
    }
    for control_key, default_value in control_defaults.items():
        if control_key not in st.session_state:
            st.session_state[control_key] = default_value
    if st.session_state[season_key] not in season_options:
        st.session_state[season_key] = season_options[0]
    if st.session_state[stat_key] not in relevant_stat_options:
        st.session_state[stat_key] = "Fantasy Points"

    year_column, stat_column = st.columns(2)
    with year_column:
        selected_season = st.selectbox(
            "Year",
            season_options,
            key=season_key,
        )
    with stat_column:
        selected_stat = st.selectbox(
            "Stat",
            relevant_stat_options,
            key=stat_key,
        )
    sync_query_params(
        league_id=league_id,
        player_id=player_id,
        year=selected_season,
        stat=selected_stat,
        source=None,
    )

    league = get_league(league_id)
    actual_rows: list[dict] = []
    predicted_rows: list[dict] = []
    weekly_stats: dict[int, dict] = {}
    data_updates = []
    try:
        weekly_stats = get_player_weekly_stats(
            player_id,
            selected_season,
            "regular",
        )
        actual_rows = build_actual_weekly_stat_rows(
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

    try:
        for week in range(1, 19):
            projected_stats = get_projected_player_stats(
                selected_season,
                week,
            ).get(player_id, {})
            predicted_rows.append(
                build_player_stat_row(
                    projected_stats,
                    league.scoring_settings,
                    week,
                )
            )
            data_updates.append(
                get_data_update("projected_player_stats", selected_season, week)
            )
    except (requests.RequestException, TypeError, ValueError):
        st.warning("ESPN projections could not be loaded.")

    try:
        schedule = get_nfl_schedule(selected_season, "regular")
        data_updates.append(get_data_update("nfl_schedule", selected_season, "regular"))
    except (requests.RequestException, TypeError, ValueError):
        schedule = []
    week_axis_labels = build_week_axis_labels(
        schedule,
        str(player.get("team") or ""),
        weekly_stats,
    )

    chart_records = [
        {
            "Week": row["Week"],
            "Week Label": week_axis_labels.get(row["Week"], f"Week {row['Week']}"),
            "Value": row[selected_stat],
            "Series": series,
        }
        for series, rows in (("Actual", actual_rows), ("Predicted", predicted_rows))
        for row in rows
    ]
    if chart_records:
        chart_data = pd.DataFrame(chart_records)
        color = alt.Color(
            "Series:N",
            title=None,
            scale=alt.Scale(
                domain=["Actual", "Predicted"],
                range=["#4c78a8", "#f58518"],
            ),
        )
        encoding = {
            "x": alt.X(
                "Week Label:N",
                sort=alt.SortField(field="Week", order="ascending"),
                axis=alt.Axis(
                    labelAngle=-45,
                    labelAlign="right",
                    labelLimit=140,
                ),
                title=None,
            ),
            "y": alt.Y("Value:Q", title=selected_stat),
            "color": color,
            "tooltip": [
                alt.Tooltip("Series:N", title="Type"),
                alt.Tooltip("Week Label:N", title="Week"),
                alt.Tooltip("Value:Q", title=selected_stat, format=".2f"),
            ],
        }
        actual_chart = (
            alt.Chart(chart_data)
            .transform_filter(alt.datum.Series == "Actual")
            .mark_line(point=True)
            .encode(**encoding)
        )
        predicted_chart = (
            alt.Chart(chart_data)
            .transform_filter(alt.datum.Series == "Predicted")
            .mark_line(point=True, strokeDash=[6, 4])
            .encode(**encoding)
        )
        chart = (actual_chart + predicted_chart).properties(height=650)
        st.altair_chart(chart, width="stretch")

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

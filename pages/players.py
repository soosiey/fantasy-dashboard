import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.data import (
    clear_player_data,
    get_league,
    get_league_users,
    get_nfl_players,
    get_player_stats,
    get_rosters,
    get_trending_players,
)
from fantasy_dashboard.player_stats import (
    build_player_identity_image,
    build_player_roster_labels,
    build_player_stat_rows,
    get_relevant_stat_labels,
    get_rosterable_positions,
)
from fantasy_dashboard.player_trends import build_player_trend_rows

# Give the player browser room for its identity, availability, and stat columns.
st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 95rem; }</style>",
    unsafe_allow_html=True,
)

league_id = st.query_params.get("league_id")
if league_id is not None:
    st.session_state["league_id"] = str(league_id)
else:
    league_id = st.session_state.get("league_id")

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

# Load stable league context before presenting league-specific player filters.
league = get_league(league_id)
rosters = get_rosters(league_id)
teams = get_league_users(league_id)
roster_labels = build_player_roster_labels(rosters.rosters, teams.users)
rosterable_positions = get_rosterable_positions(league.roster_positions)
season = league.season
season_type = league.season_type

# Keep the force-refresh control compact and separate from the player filters.
title_column, refresh_column = st.columns([8, 1], vertical_alignment="center")
with title_column:
    st.title("Players")
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-players",
        help="Reload player availability and statistics from Sleeper",
        width="content",
    )

players_list_tab, trends_tab = st.tabs(["Players list", "Trends"])

with players_list_tab:
    # Filter current availability independently from the selected statistics period.
    availability_column, position_column, period_column, week_column = st.columns(4)
    with availability_column:
        available_only = st.toggle("Available players only")
    with position_column:
        selected_position_label = st.selectbox(
            "Position",
            ["All Positions", *rosterable_positions],
        )
    with period_column:
        stats_period = st.segmented_control(
            "Statistics",
            ["Season", "Week"],
            default="Season",
            width="stretch",
        )
    with week_column:
        selected_week = (
            st.selectbox(
                "Week",
                range(1, 19),
                format_func=lambda week: f"Week {week}",
            )
            if stats_period == "Week"
            else None
        )

    player_search = st.text_input(
        "Player name",
        placeholder="Search by player name",
    )

    if force_refresh:
        clear_player_data(league_id, season, season_type, selected_week)
        st.rerun()

    # Load the selected aggregate and join it to current league ownership.
    try:
        stats_by_player_id = get_player_stats(
            season,
            season_type,
            selected_week,
        )
    except (requests.RequestException, TypeError, ValueError):
        stats_by_player_id = {}
        st.warning("Player statistics could not be loaded; values default to zero.")

    selected_position = (
        None
        if selected_position_label == "All Positions"
        else selected_position_label
    )
    nfl_players = get_nfl_players()
    player_rows = build_player_stat_rows(
        nfl_players,
        rosters.rosters,
        stats_by_player_id,
        league.scoring_settings,
        rosterable_positions,
        selected_position=selected_position,
        available_only=available_only,
        roster_labels_by_player_id=roster_labels,
    )
    search_query = player_search.strip().casefold()
    if search_query:
        player_rows = [
            row
            for row in player_rows
            if search_query in str(row["Player"]).casefold()
        ]

    st.caption(
        f"{len(player_rows):,} players · Availability reflects the league's current "
        "rosters, regardless of the selected statistics week."
    )
    if not player_rows:
        st.info("No players match the selected filters.")
    else:
        player_table = pd.DataFrame(player_rows)
        player_table["Player"] = [
            build_player_identity_image(player, owner)
            for player, owner in zip(
                player_table["Player"], player_table["Roster"]
            )
        ]
        player_table = player_table.drop(columns="Roster")

        # Subtly emphasize each row's position-relevant statistics.
        def highlight_relevant_stats(row: pd.Series) -> list[str]:
            relevant_columns = get_relevant_stat_labels(str(row["Position"]))
            return [
                "background-color: rgba(59, 130, 246, 0.10)"
                if column in relevant_columns
                else ""
                for column in row.index
            ]

        styled_player_table = player_table.style.apply(
            highlight_relevant_stats, axis=1
        )
        st.dataframe(
            styled_player_table,
            column_config={
                "Player": st.column_config.ImageColumn("Player", width="large"),
                "Position": st.column_config.TextColumn("Pos", width="small"),
                "Team": st.column_config.TextColumn("Team", width="small"),
                "Availability": st.column_config.TextColumn(
                    "Availability", width="small"
                ),
                "Fantasy Points": st.column_config.NumberColumn(
                    "Fantasy Points",
                    format="%.2f",
                    width="small",
                ),
            },
            hide_index=True,
            height=700,
            width="stretch",
        )

with trends_tab:
    st.caption("Most added and dropped NFL players over the past 48 hours.")
    try:
        added_players = get_trending_players("add", 48, 25)
        dropped_players = get_trending_players("drop", 48, 25)
    except (requests.RequestException, TypeError, ValueError):
        st.warning("Trending player data could not be loaded.")
    else:
        nfl_players = get_nfl_players()
        trend_columns = {
            "Player": st.column_config.ImageColumn("Player", width="large"),
            "Position": st.column_config.TextColumn("Pos", width="small"),
            "Team": st.column_config.TextColumn("Team", width="small"),
        }
        adds_column, drops_column = st.columns(2)
        with adds_column:
            st.subheader("Adds")
            adds_frame = pd.DataFrame(
                build_player_trend_rows(
                    added_players, nfl_players, "Adds", roster_labels
                ),
                columns=["Player", "Roster", "Position", "Team", "Adds"],
            )
            adds_frame["Player"] = [
                build_player_identity_image(player, owner)
                for player, owner in zip(
                    adds_frame["Player"], adds_frame["Roster"]
                )
            ]
            adds_table = adds_frame.drop(columns="Roster").style.format(
                {"Adds": lambda count: f"{count} ↑"}
            ).map(
                lambda _: "color: #16a34a; font-weight: 600;",
                subset=["Adds"],
            )
            st.dataframe(
                adds_table,
                column_config={
                    **trend_columns,
                    "Adds": st.column_config.Column("Adds", width="small"),
                },
                hide_index=True,
                height=700,
                width="stretch",
            )
        with drops_column:
            st.subheader("Drops")
            drops_frame = pd.DataFrame(
                build_player_trend_rows(
                    dropped_players, nfl_players, "Drops", roster_labels
                ),
                columns=["Player", "Roster", "Position", "Team", "Drops"],
            )
            drops_frame["Player"] = [
                build_player_identity_image(player, owner)
                for player, owner in zip(
                    drops_frame["Player"], drops_frame["Roster"]
                )
            ]
            drops_table = drops_frame.drop(columns="Roster").style.format(
                {"Drops": lambda count: f"{count} ↓"}
            ).map(
                lambda _: "color: #dc2626; font-weight: 600;",
                subset=["Drops"],
            )
            st.dataframe(
                drops_table,
                column_config={
                    **trend_columns,
                    "Drops": st.column_config.Column("Drops", width="small"),
                },
                hide_index=True,
                height=700,
                width="stretch",
            )
        st.caption("Trending data provided by Sleeper.")

# Keep league and account navigation available beneath the player browser.
with st.bottom:
    league_change = st.button("Switch Leagues")
    reset = st.button("Log Out")

if league_change:
    st.session_state.pop("league_id")
    if "league_id" in st.query_params:
        st.query_params.pop("league_id")
    st.switch_page("pages/leagues.py")
if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

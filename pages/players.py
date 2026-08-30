import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.comparison_selection import (
    COMPARISON_COLUMN,
    add_comparison_column,
    render_comparison_column_label,
    render_comparison_sidebar,
    save_comparison_selection,
)
from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.player_details import show_player_details
from fantasy_dashboard.components.player_news import show_player_news
from fantasy_dashboard.data import (
    clear_player_data,
    clear_projected_player_data,
    get_data_update,
    get_default_nfl_week,
    get_league,
    get_league_users,
    get_nfl_players,
    get_player_stats,
    get_projected_player_stats,
    get_rosters,
    get_trending_players,
)
from fantasy_dashboard.player_stats import (
    ALL_STATS,
    build_player_identity_image,
    build_player_roster_labels,
    build_player_stat_rows,
    get_relevant_stat_labels,
    get_rosterable_positions,
)
from fantasy_dashboard.player_trends import build_player_trend_rows
from fantasy_dashboard.roster import get_player_by_id
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    require_authentication,
    resolve_league_id,
    sync_query_params,
)


# Resolve a dataframe button click to the player ID at the same row position.
def open_player_from_button(
    click_key: str,
    player_ids: list[str],
    state_key: str = "_selected_player_id",
) -> None:
    click = st.session_state.get(click_key)
    if not click:
        return
    selected_row = int(click["row"])
    if 0 <= selected_row < len(player_ids):
        st.session_state[state_key] = player_ids[selected_row]


# Give the player browser room for its identity, availability, and stat columns.
st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 95rem; }</style>",
    unsafe_allow_html=True,
)

require_authentication("players")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

analysis_mode = bool(st.session_state.get(ANALYSIS_MODE_KEY))

# Load stable league context before presenting league-specific player filters.
league = get_league(league_id)
rosters = get_rosters(league_id)
teams = get_league_users(league_id)
roster_labels = build_player_roster_labels(rosters.rosters, teams.users)
rosterable_positions = get_rosterable_positions(league.roster_positions)
season = league.season
season_type = league.season_type
try:
    current_week = get_default_nfl_week(season)
except (requests.RequestException, KeyError, TypeError, ValueError):
    current_week = 1

requested_stats_source = str(st.query_params.get("stats") or "actual").casefold()
requested_period = str(st.query_params.get("period") or "season").casefold()
requested_position = str(st.query_params.get("position") or "")
requested_availability = str(st.query_params.get("availability") or "").casefold()
try:
    requested_week = int(st.query_params.get("week") or current_week)
except (TypeError, ValueError):
    requested_week = current_week
requested_week = min(max(requested_week, 1), 18)
filter_prefix = f"players-{league_id}"
position_filter_options = ["All Positions", "FLEX", *rosterable_positions]
available_filter_key = f"{filter_prefix}-available-only"
stats_source_filter_key = f"{filter_prefix}-stat-source"
position_filter_key = f"{filter_prefix}-position"
period_filter_key = f"{filter_prefix}-period"
week_filter_key = f"{filter_prefix}-week-v3-{season}"
search_filter_key = f"{filter_prefix}-search"

player_filter_defaults = {
    available_filter_key: requested_availability == "available",
    stats_source_filter_key: (
        "Predicted" if requested_stats_source == "predicted" else "Actual"
    ),
    position_filter_key: (
        requested_position
        if requested_position in position_filter_options
        else "All Positions"
    ),
    period_filter_key: "Week" if requested_period == "week" else "Season",
    week_filter_key: requested_week,
    search_filter_key: str(st.query_params.get("search") or ""),
}
for filter_key, default_value in player_filter_defaults.items():
    if filter_key not in st.session_state:
        st.session_state[filter_key] = default_value

# Keep the force-refresh control compact and separate from the player filters.
title_column, refresh_column = st.columns([8, 1], vertical_alignment="center")
with title_column:
    st.title("Players")
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-players",
        help="Reload player availability and cached statistics",
        width="content",
    )

players_list_tab, trends_tab = st.tabs(["Players list", "Trends"])

with players_list_tab:
    # Filter current availability independently from the selected statistics period.
    availability_column, position_column, period_column, week_column = st.columns(4)
    with availability_column:
        available_only = st.toggle("Available players only", key=available_filter_key)
        stats_source = st.segmented_control(
            "Stat type",
            ["Actual", "Predicted"],
            key=stats_source_filter_key,
            width="stretch",
        )
    with position_column:
        selected_position_label = st.selectbox(
            "Position",
            position_filter_options,
            key=position_filter_key,
        )
    with period_column:
        stats_period = st.segmented_control(
            "Period",
            ["Season", "Week"],
            key=period_filter_key,
            width="stretch",
        )
    with week_column:
        selected_week = (
            st.selectbox(
                "Week",
                range(1, 19),
                index=current_week - 1,
                format_func=lambda week: f"Week {week}",
                key=week_filter_key,
            )
            if stats_period == "Week"
            else None
        )

    player_search = st.text_input(
        "Player name",
        placeholder="Search by player name",
        key=search_filter_key,
    )

    sync_query_params(
        league_id=league_id,
        availability="available" if available_only else None,
        position=(
            selected_position_label
            if selected_position_label != "All Positions"
            else None
        ),
        period=stats_period.casefold(),
        week=selected_week,
        stats=stats_source.casefold(),
        search=player_search.strip() or None,
    )

    if force_refresh:
        clear_player_data(league_id, season, season_type, selected_week)
        if stats_source == "Predicted":
            clear_projected_player_data(season, selected_week)
        st.rerun()

    # Load actual or projected aggregates and join them to league ownership.
    try:
        if stats_source == "Predicted":
            stats_by_player_id = get_projected_player_stats(
                season,
                selected_week,
            )
        else:
            stats_by_player_id = get_player_stats(
                season,
                season_type,
                selected_week,
            )
    except (requests.RequestException, TypeError, ValueError):
        stats_by_player_id = {}
        source_name = (
            "ESPN projections" if stats_source == "Predicted" else "Player statistics"
        )
        st.warning(f"{source_name} could not be loaded; values default to zero.")

    selected_position = (
        None if selected_position_label == "All Positions" else selected_position_label
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
            row for row in player_rows if search_query in str(row["Player"]).casefold()
        ]

    st.caption(
        f"{len(player_rows):,} players · "
        f"{'Predictions provided by ESPN' if stats_source == 'Predicted' else 'Actual statistics provided by Sleeper'}"
        " · Availability reflects the league's current rosters."
    )
    if not player_rows:
        st.info("No players match the selected filters.")
    else:
        player_table = pd.DataFrame(player_rows)
        player_ids = player_table["Player ID"].astype(str).tolist()
        player_table["Player"] = [
            build_player_identity_image(player, owner)
            for player, owner in zip(player_table["Player"], player_table["Roster"])
        ]
        player_table = player_table.drop(columns="Roster")
        player_table.insert(2, "Details", "View")
        player_table.insert(
            player_table.columns.get_loc("Fantasy Points"),
            "News",
            "View",
        )
        if analysis_mode:
            player_table = add_comparison_column(
                player_table,
                player_ids,
                league_id,
            )

        # Subtly emphasize each row's position-relevant statistics.
        def highlight_relevant_stats(row: pd.Series) -> list[str]:
            relevant_columns = get_relevant_stat_labels(str(row["Position"]))
            return [
                (
                    "background-color: rgba(59, 130, 246, 0.10)"
                    if column in relevant_columns
                    else ""
                )
                for column in row.index
            ]

        styled_player_table = player_table.style.apply(highlight_relevant_stats, axis=1)
        player_column_config = {
            **(
                {
                    COMPARISON_COLUMN: st.column_config.CheckboxColumn(
                        "",
                        width="small",
                    )
                }
                if analysis_mode
                else {}
            ),
            **{
                label: st.column_config.NumberColumn(
                    label,
                    format="%.2f",
                    width="small",
                )
                for label, _ in ALL_STATS
            },
            "Player ID": None,
            "Player": st.column_config.ImageColumn("Player", width=260),
            "Details": st.column_config.ButtonColumn(
                "",
                width="small",
                type="secondary",
                on_click=open_player_from_button,
                args=("players-list-click", player_ids),
                key="players-list-click",
            ),
            "News": st.column_config.ButtonColumn(
                "Recent News",
                width="small",
                type="secondary",
                on_click=open_player_from_button,
                args=(
                    "players-news-click",
                    player_ids,
                    "_selected_news_player_id",
                ),
                key="players-news-click",
            ),
            "Position": st.column_config.TextColumn("Pos", width="small"),
            "Team": st.column_config.TextColumn("Team", width="small"),
            "Availability": st.column_config.TextColumn("Availability", width="small"),
            "Fantasy Points": st.column_config.NumberColumn(
                "Fantasy Points",
                format="%.2f",
                width="small",
            ),
        }
        if analysis_mode:
            render_comparison_column_label()
            edited_player_table = st.data_editor(
                styled_player_table,
                column_config=player_column_config,
                disabled=[
                    column
                    for column in player_table.columns
                    if column not in {COMPARISON_COLUMN, "Details", "News"}
                ],
                hide_index=True,
                height=700,
                width="stretch",
                key="analysis-players-list-table",
            )
            save_comparison_selection(
                edited_player_table,
                player_ids,
                league_id,
            )
        else:
            st.dataframe(
                styled_player_table,
                column_config=player_column_config,
                hide_index=True,
                height=700,
                width="stretch",
                key="players-list-table",
            )

    if analysis_mode:
        render_comparison_sidebar(nfl_players, league_id)

    stats_update = (
        get_data_update("projected_player_stats", season, selected_week)
        if stats_source == "Predicted"
        else get_data_update("player_stats", season, season_type, selected_week)
    )
    render_data_disclaimer(
        stats_update,
        get_data_update("rosters", league_id),
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
            "Player": st.column_config.ImageColumn("Player", width=260),
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
            adds_frame["Player ID"] = [
                str(trend["player_id"]) for trend in added_players
            ]
            add_player_ids = adds_frame["Player ID"].tolist()
            adds_frame["Player"] = [
                build_player_identity_image(player, owner)
                for player, owner in zip(adds_frame["Player"], adds_frame["Roster"])
            ]
            adds_frame = adds_frame.drop(columns="Roster")
            adds_frame.insert(1, "Details", "View")
            adds_table = adds_frame.style.format(
                {"Adds": lambda count: f"{count} ↑"}
            ).map(
                lambda _: "color: #16a34a; font-weight: 600;",
                subset=["Adds"],
            )
            st.dataframe(
                adds_table,
                column_config={
                    **trend_columns,
                    "Player ID": None,
                    "Details": st.column_config.ButtonColumn(
                        "",
                        width="small",
                        type="secondary",
                        on_click=open_player_from_button,
                        args=("player-adds-click", add_player_ids),
                        key="player-adds-click",
                    ),
                    "Adds": st.column_config.Column("Adds", width="small"),
                },
                hide_index=True,
                height=700,
                width="stretch",
                key="player-adds-table",
            )
        with drops_column:
            st.subheader("Drops")
            drops_frame = pd.DataFrame(
                build_player_trend_rows(
                    dropped_players, nfl_players, "Drops", roster_labels
                ),
                columns=["Player", "Roster", "Position", "Team", "Drops"],
            )
            drops_frame["Player ID"] = [
                str(trend["player_id"]) for trend in dropped_players
            ]
            drop_player_ids = drops_frame["Player ID"].tolist()
            drops_frame["Player"] = [
                build_player_identity_image(player, owner)
                for player, owner in zip(drops_frame["Player"], drops_frame["Roster"])
            ]
            drops_frame = drops_frame.drop(columns="Roster")
            drops_frame.insert(1, "Details", "View")
            drops_table = drops_frame.style.format(
                {"Drops": lambda count: f"{count} ↓"}
            ).map(
                lambda _: "color: #dc2626; font-weight: 600;",
                subset=["Drops"],
            )
            st.dataframe(
                drops_table,
                column_config={
                    **trend_columns,
                    "Player ID": None,
                    "Details": st.column_config.ButtonColumn(
                        "",
                        width="small",
                        type="secondary",
                        on_click=open_player_from_button,
                        args=("player-drops-click", drop_player_ids),
                        key="player-drops-click",
                    ),
                    "Drops": st.column_config.Column("Drops", width="small"),
                },
                hide_index=True,
                height=700,
                width="stretch",
                key="player-drops-table",
            )
        st.caption("Trending data provided by Sleeper.")
        render_data_disclaimer(
            get_data_update("trending_players", "add", 48, 25),
            get_data_update("trending_players", "drop", 48, 25),
        )

selected_player_id = st.session_state.pop("_selected_player_id", None)
if selected_player_id:
    selected_player = nfl_players.get(str(selected_player_id))
    if selected_player is None:
        st.warning("That player could not be found in the local player cache.")
    else:
        show_player_details(
            str(selected_player_id),
            selected_player,
            season,
            season_type,
            league.scoring_settings,
        )

selected_news_player_id = st.session_state.pop("_selected_news_player_id", None)
if selected_news_player_id:
    news_player = get_player_by_id(nfl_players, str(selected_news_player_id))
    if news_player is None:
        st.warning("That player could not be found in the local player cache.")
    else:
        show_player_news(news_player)

# Keep the current app state's only valid exits beneath the player browser.
with st.bottom:
    if analysis_mode:
        back_to_overview = st.button("Back to Overview")
    else:
        league_change = st.button("Switch Leagues")
        reset = st.button("Log Out")

if analysis_mode and back_to_overview:
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.switch_page(
        "pages/overview.py",
        query_params={"league_id": league_id},
    )
if not analysis_mode and league_change:
    st.session_state.pop("league_id", None)
    st.session_state.pop("user_id", None)
    if "league_id" in st.query_params:
        st.query_params.pop("league_id")
    st.switch_page("pages/leagues.py")
if not analysis_mode and reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

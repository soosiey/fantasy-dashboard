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
    get_avatar,
    get_data_update,
    get_default_nfl_week,
    get_league,
    get_league_users,
    get_nfl_players,
    get_player_stats,
    get_projected_player_stats,
    get_rosters,
)
from fantasy_dashboard.player_stats import (
    ALL_STATS,
    build_player_identity_image,
    build_player_roster_labels,
    build_player_stat_rows,
    get_relevant_stat_labels,
    get_rosterable_positions,
)
from fantasy_dashboard.roster import get_player_by_id, get_roster_player_order
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    require_authentication,
    resolve_league_id,
    sync_query_params,
)


def open_player_from_button(
    click_key: str,
    player_ids: list[str],
    state_key: str,
) -> None:
    click = st.session_state.get(click_key)
    if not click:
        return
    selected_row = int(click["row"])
    if 0 <= selected_row < len(player_ids):
        st.session_state[state_key] = player_ids[selected_row]


current_user = require_authentication("analysis")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

if not st.session_state.get(ANALYSIS_MODE_KEY):
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.rerun()

st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 95rem; }</style>",
    unsafe_allow_html=True,
)
st.title("Statistics")

league = get_league(league_id)
rosters = get_rosters(league_id)
teams = get_league_users(league_id)
rosterable_positions = get_rosterable_positions(league.roster_positions)
try:
    current_week = get_default_nfl_week(league.season)
except (requests.RequestException, KeyError, TypeError, ValueError):
    current_week = 1

requested_stats_source = str(st.query_params.get("stats") or "actual").casefold()
requested_period = str(st.query_params.get("period") or "season").casefold()
requested_position = str(st.query_params.get("position") or "")
try:
    requested_week = int(st.query_params.get("week") or current_week)
except (TypeError, ValueError):
    requested_week = current_week
requested_week = min(max(requested_week, 1), 18)

filter_prefix = f"statistics-{league_id}"
stats_source_filter_key = f"{filter_prefix}-stat-source"
position_filter_key = f"{filter_prefix}-position"
period_filter_key = f"{filter_prefix}-period"
week_filter_key = f"{filter_prefix}-week-v3-{league.season}"
filter_defaults = {
    stats_source_filter_key: (
        "Predicted" if requested_stats_source == "predicted" else "Actual"
    ),
    position_filter_key: (
        requested_position
        if requested_position in rosterable_positions
        else "All Positions"
    ),
    period_filter_key: "Week" if requested_period == "week" else "Season",
    week_filter_key: requested_week,
}
for filter_key, default_value in filter_defaults.items():
    if filter_key not in st.session_state:
        st.session_state[filter_key] = default_value

rosters_by_user_id = {roster.user_id: roster for roster in rosters.rosters}
selectable_teams = [team for team in teams.users if team.user_id in rosters_by_user_id]
teams_by_user_id = {team.user_id: team for team in selectable_teams}
team_user_ids = list(teams_by_user_id)

if not team_user_ids:
    st.warning("No teams with rosters were found in this league.")
else:
    requested_team_id = str(st.query_params.get("team") or "")
    default_team_id = (
        current_user.user_id
        if current_user.user_id in teams_by_user_id
        else team_user_ids[0]
    )
    if requested_team_id in teams_by_user_id:
        default_team_id = requested_team_id

    team_selector_key = f"statistics-team-{league_id}"
    if st.session_state.get(team_selector_key) not in teams_by_user_id:
        st.session_state[team_selector_key] = default_team_id

    selected_user_id = st.selectbox(
        "Team",
        team_user_ids,
        format_func=lambda user_id: teams_by_user_id[user_id].display_team_name,
        key=team_selector_key,
    )

    selected_team = teams_by_user_id[selected_user_id]
    selected_roster = rosters_by_user_id[selected_user_id]

    team_icon, team_identity = st.columns([1, 5], vertical_alignment="center")
    with team_icon:
        st.image(get_avatar(selected_team.avatar_id), width=112)
    with team_identity:
        st.subheader(selected_team.display_team_name)
        st.caption(f"Owner: {selected_team.display_name}")

    stats_source_column, position_column, period_column, week_column = st.columns(4)
    with stats_source_column:
        stats_source = st.segmented_control(
            "Stat type",
            ["Actual", "Predicted"],
            key=stats_source_filter_key,
            width="stretch",
        )
    with position_column:
        selected_position_label = st.selectbox(
            "Position",
            ["All Positions", *rosterable_positions],
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

    sync_query_params(
        league_id=league_id,
        team=selected_user_id,
        position=(
            selected_position_label
            if selected_position_label != "All Positions"
            else None
        ),
        period=stats_period.casefold(),
        week=selected_week,
        stats=stats_source.casefold(),
    )

    try:
        if stats_source == "Predicted":
            stats_by_player_id = get_projected_player_stats(
                league.season,
                selected_week,
            )
        else:
            stats_by_player_id = get_player_stats(
                league.season,
                league.season_type,
                selected_week,
            )
    except (requests.RequestException, TypeError, ValueError):
        stats_by_player_id = {}
        source_name = (
            "ESPN projections" if stats_source == "Predicted" else "Player statistics"
        )
        st.warning(f"{source_name} could not be loaded; values default to zero.")

    nfl_players = get_nfl_players()
    roster_labels = build_player_roster_labels(rosters.rosters, teams.users)
    selected_position = (
        None if selected_position_label == "All Positions" else selected_position_label
    )
    roster_player_order = get_roster_player_order(selected_roster)
    selected_player_ids = set(roster_player_order)
    player_rows = [
        row
        for row in build_player_stat_rows(
            nfl_players,
            rosters.rosters,
            stats_by_player_id,
            league.scoring_settings,
            rosterable_positions,
            selected_position=selected_position,
            roster_labels_by_player_id=roster_labels,
        )
        if row["Player ID"] in selected_player_ids
    ]
    roster_order_by_player_id = {
        player_id: index for index, player_id in enumerate(roster_player_order)
    }
    player_rows.sort(
        key=lambda row: roster_order_by_player_id.get(
            row["Player ID"], len(roster_player_order)
        )
    )

    st.subheader("Players")
    if not player_rows:
        st.info("No active players were found on this roster.")
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
        player_table = add_comparison_column(
            player_table,
            player_ids,
            league_id,
        )

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

        render_comparison_column_label()
        edited_player_table = st.data_editor(
            player_table.style.apply(highlight_relevant_stats, axis=1),
            column_config={
                COMPARISON_COLUMN: st.column_config.CheckboxColumn(
                    "",
                    width="small",
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
                    args=(
                        "statistics-details-click",
                        player_ids,
                        "_statistics_details_player_id",
                    ),
                    key="statistics-details-click",
                ),
                "News": st.column_config.ButtonColumn(
                    "Recent News",
                    width="small",
                    type="secondary",
                    on_click=open_player_from_button,
                    args=(
                        "statistics-news-click",
                        player_ids,
                        "_statistics_news_player_id",
                    ),
                    key="statistics-news-click",
                ),
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
            disabled=[
                column
                for column in player_table.columns
                if column not in {COMPARISON_COLUMN, "Details", "News"}
            ],
            hide_index=True,
            height=700,
            width="stretch",
            key="statistics-player-table",
        )
        save_comparison_selection(
            edited_player_table,
            player_ids,
            league_id,
        )

        selected_details_player_id = st.session_state.pop(
            "_statistics_details_player_id", None
        )
        if selected_details_player_id:
            selected_player = nfl_players.get(str(selected_details_player_id))
            if selected_player is None:
                st.warning("That player could not be found in the local player cache.")
            else:
                show_player_details(
                    str(selected_details_player_id),
                    selected_player,
                    league.season,
                    league.season_type,
                    league.scoring_settings,
                )

        selected_news_player_id = st.session_state.pop(
            "_statistics_news_player_id", None
        )
        if selected_news_player_id:
            news_player = get_player_by_id(
                nfl_players,
                str(selected_news_player_id),
            )
            if news_player is None:
                st.warning("That player could not be found in the local player cache.")
            else:
                show_player_news(news_player)

    render_comparison_sidebar(nfl_players, league_id)

    render_data_disclaimer(
        (
            get_data_update("projected_player_stats", league.season, selected_week)
            if stats_source == "Predicted"
            else get_data_update(
                "player_stats",
                league.season,
                league.season_type,
                selected_week,
            )
        ),
        get_data_update("rosters", league_id),
    )

with st.bottom:
    back_to_overview = st.button("Back to Overview")

if back_to_overview:
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.switch_page(
        "pages/overview.py",
        query_params={"league_id": league_id},
    )

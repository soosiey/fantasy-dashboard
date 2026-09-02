from dataclasses import fields
from html import escape
from urllib.parse import quote

import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.data import (
    clear_league_data,
    get_data_update,
    get_league,
    get_league_users,
    get_rosters,
)
from fantasy_dashboard.routing import require_authentication, resolve_league_id
from fantasy_dashboard.scoring import (
    ScoringSection,
    get_scoring_section,
    get_scoring_sort_key,
)

require_authentication("overview")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

title_column, refresh_column = st.columns([8, 1], vertical_alignment="center")
with title_column:
    st.title("Overview")
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-overview",
        help="Reload league settings and teams from Sleeper",
        width="content",
    )

if force_refresh:
    clear_league_data(league_id)
    st.rerun()

league = get_league(league_id)
st.write(f"League: {league.name}")

# Split the league overview into team browsing and settings views.
teams_tab, settings_tab = st.tabs(["Teams", "Settings"])

with teams_tab:
    # Match league members to roster owners before rendering the team-card grid.
    teams = get_league_users(league_id)
    rosters = get_rosters(league_id)
    roster_owner_ids = {roster.user_id for roster in rosters.rosters}
    visible_teams = [team for team in teams.users if team.user_id in roster_owner_ids]

    st.markdown(
        """
        <style>
            [class*="st-key-overview-team-card-"] {
                min-height: 10.5rem;
            }
            [class*="st-key-overview-team-card-"] [data-testid="stVerticalBlock"] {
                gap: 0.3rem;
            }
            .overview-team-avatar-wrap {
                display: flex;
                justify-content: center;
                width: 100%;
            }
            .overview-team-avatar,
            .overview-team-avatar-fallback {
                width: 3.5rem;
                height: 3.5rem;
                border-radius: 50%;
            }
            .overview-team-avatar {
                object-fit: cover;
            }
            .overview-team-avatar-fallback {
                align-items: center;
                background: rgba(128, 128, 128, 0.14);
                display: flex;
                font-size: 1.6rem;
                justify-content: center;
            }
            [class*="st-key-overview-team-card-"]
            [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {
                display: flex;
                justify-content: center;
                width: 100%;
            }
            [class*="st-key-overview-team-card-"] [data-testid="stPageLink"] {
                display: flex;
                justify-content: center;
                width: 100%;
            }
            [class*="st-key-overview-team-card-"] [data-testid="stPageLink"] a {
                justify-content: center;
                margin: 0.25rem auto 0;
                min-height: 1.8rem;
                padding: 0.25rem 0.4rem;
                font-size: 0.72rem;
                width: fit-content;
            }
            .overview-team-name,
            .overview-team-owner {
                overflow: hidden;
                text-align: center;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .overview-team-name {
                font-size: 0.82rem;
                font-weight: 650;
                line-height: 1.1rem;
            }
            .overview-team-owner {
                color: #808495;
                font-size: 0.68rem;
                line-height: 0.9rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for row_start in range(0, len(visible_teams), 5):
        team_columns = st.columns(5, gap="small")
        for column, team in zip(team_columns, visible_teams[row_start : row_start + 5]):
            with column, st.container(
                border=True,
                key=f"overview-team-card-{team.user_id}",
            ):
                avatar_id = str(team.avatar_id or "")
                avatar = (
                    '<img class="overview-team-avatar" '
                    f'src="{SleeperClient.AVATAR_URL}/{quote(avatar_id, safe="")}" '
                    f'alt="{escape(team.display_team_name)} avatar">'
                    if avatar_id and avatar_id != "None"
                    else '<span class="overview-team-avatar-fallback">🏈</span>'
                )
                st.markdown(
                    f'<div class="overview-team-avatar-wrap">{avatar}</div>'
                    '<div class="overview-team-name" '
                    f'title="{escape(team.display_team_name)}">'
                    f"{escape(team.display_team_name)}</div>"
                    '<div class="overview-team-owner" '
                    f'title="{escape(team.display_name)}">'
                    f"{escape(team.display_name)}</div>",
                    unsafe_allow_html=True,
                )
                st.page_link(
                    "pages/team.py",
                    label="View Team",
                    width="stretch",
                    query_params={
                        "league_id": league_id,
                        "user_id": team.user_id,
                    },
                )

with settings_tab:
    # Separate general league configuration from the larger scoring-rule set.
    league_settings_tab, scoring_settings_tab = st.tabs(
        ["League Settings", "Scoring Settings"]
    )

    with league_settings_tab:
        # Convert the settings model into a compact, right-aligned table.
        league_settings = [
            {
                "Setting": setting.name.replace("_", " ").title(),
                "Value": str(getattr(league.settings, setting.name)),
            }
            for setting in fields(league.settings)
        ]
        st.dataframe(
            league_settings,
            column_config={
                "Setting": st.column_config.TextColumn("Setting", width="large"),
                "Value": st.column_config.TextColumn(
                    "Value", width="small", alignment="right"
                ),
            },
            hide_index=True,
            width="stretch",
        )

    with scoring_settings_tab:
        # Group and rank every scoring rule before rendering section tables.
        grouped_scoring_settings = {section: [] for section in ScoringSection}
        for setting, value in league.scoring_settings.items():
            section = get_scoring_section(setting)
            grouped_scoring_settings[section].append((setting, value))

        for section, section_settings in grouped_scoring_settings.items():
            if not section_settings:
                continue
            st.subheader(section.value)
            scoring_table = [
                {
                    "Setting": setting.replace("_", " ").title(),
                    "Points": value,
                }
                for setting, value in sorted(
                    section_settings,
                    key=lambda item: get_scoring_sort_key(section, item[0]),
                )
            ]
            st.dataframe(
                scoring_table,
                column_config={
                    "Setting": st.column_config.TextColumn("Setting", width="large"),
                    "Points": st.column_config.NumberColumn(
                        "Points", width="small", alignment="right"
                    ),
                },
                hide_index=True,
                width="stretch",
            )

render_data_disclaimer(
    get_data_update("league", league_id),
    get_data_update("league_users", league_id),
    get_data_update("rosters", league_id),
)

# Keep league and account navigation available beneath either tab.
with st.bottom:
    league_change = st.button("Switch Leagues")
    reset = st.button("Log Out")

if league_change:
    st.session_state.pop("league_id", None)
    st.session_state.pop("user_id", None)
    if "league_id" in st.query_params:
        st.query_params.pop("league_id")
    st.switch_page("pages/leagues.py")
if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

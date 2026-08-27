from dataclasses import fields

import streamlit as st

from fantasy_dashboard.data import (
    clear_league_data,
    get_avatar,
    get_league,
    get_league_users,
    get_rosters,
)
from fantasy_dashboard.scoring import (
    ScoringSection,
    get_scoring_section,
    get_scoring_sort_key,
)

league_id = st.query_params.get("league_id")

if league_id is not None:
    st.session_state["league_id"] = str(league_id)
else:
    league_id = st.session_state["league_id"]

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

    for row_start in range(0, len(visible_teams), 2):
        team_columns = st.columns(2, gap="large")
        for column, team in zip(team_columns, visible_teams[row_start : row_start + 2]):
            with column, st.container(border=True, height=280):
                image = get_avatar(team.avatar_id)
                st.image(image, width=96)
                st.subheader(team.display_team_name)
                st.caption(team.display_name)
                st.page_link(
                    "pages/team.py",
                    label="View Team",
                    query_params={"user_id": team.user_id},
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

# Keep league and account navigation available beneath either tab.
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

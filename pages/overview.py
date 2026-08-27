from dataclasses import fields

import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.scoring import (
    ScoringSection,
    get_scoring_section,
    get_scoring_sort_key,
)

if "client" not in st.session_state:
    client = SleeperClient()
else:
    client = st.session_state.get("client")

league_id = st.query_params.get("league_id")

if league_id is not None:
    st.session_state["league_id"] = str(league_id)
else:
    league_id = st.session_state["league_id"]

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

st.title("Overview")
league = client.get_single_league(league_id)
st.write(f"League: {league.name}")

teams_tab, settings_tab = st.tabs(["Teams", "Settings"])

with teams_tab:
    teams = client.get_all_users(league_id)
    rosters = client.get_all_rosters(league_id)
    roster_owner_ids = {roster.user_id for roster in rosters.rosters}
    visible_teams = [team for team in teams.users if team.user_id in roster_owner_ids]

    for row_start in range(0, len(visible_teams), 2):
        team_columns = st.columns(2, gap="large")
        for column, team in zip(team_columns, visible_teams[row_start : row_start + 2]):
            with column:
                with st.container(border=True, height=280):
                    image = client.get_avatar(team.avatar_id)
                    st.image(image, width=96)
                    st.subheader(team.display_team_name)
                    st.caption(team.display_name)
                    st.page_link(
                        "pages/team.py",
                        label="View Team",
                        query_params={"user_id": team.user_id},
                    )

with settings_tab:
    league_settings_tab, scoring_settings_tab = st.tabs(
        ["League Settings", "Scoring Settings"]
    )

    with league_settings_tab:
        for setting in fields(league.settings):
            label = setting.name.replace("_", " ").title()
            st.write(f"**{label}:** {getattr(league.settings, setting.name)}")

    with scoring_settings_tab:
        grouped_scoring_settings = {section: [] for section in ScoringSection}
        for setting, value in league.scoring_settings.items():
            section = get_scoring_section(setting)
            grouped_scoring_settings[section].append((setting, value))

        for section, section_settings in grouped_scoring_settings.items():
            if not section_settings:
                continue
            st.subheader(section.value)
            for setting, value in sorted(
                section_settings,
                key=lambda item: get_scoring_sort_key(section, item[0]),
            ):
                label = setting.replace("_", " ").title()
                st.write(f"**{label}:** {value}")

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

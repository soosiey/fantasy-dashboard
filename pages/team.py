import json
from html import escape
from textwrap import dedent

import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.paths import NFL_PLAYERS_PATH
from fantasy_dashboard.roster import build_roster_rows


# Render roster rows as a borderless, zebra-striped table.
def render_roster_table(rows: list[tuple[str, str, str | None]]) -> None:
    table_rows = "".join(
        "<tr>"
        f'<td class="roster-position">{escape(position)}</td>'
        f"<td>{escape(player_name)}"
        + (
            f'<span class="player-position">{escape(player_position)}</span>'
            if player_position
            else ""
        )
        + "</td>"
        "</tr>"
        for position, player_name, player_position in rows
    )
    st.markdown(
        dedent(f"""
        <style>
            .roster-table {{
                border-collapse: collapse;
                color: inherit;
                width: 100%;
            }}
            .roster-table th,
            .roster-table td {{
                border: none;
                padding: 0.65rem 0.85rem;
                text-align: left;
            }}
            .roster-table th {{
                color: #808495;
                font-size: 0.8rem;
                text-transform: uppercase;
            }}
            .roster-table tbody tr:nth-child(odd) {{
                background-color: rgba(128, 128, 128, 0.10);
            }}
            .roster-table tbody tr:nth-child(even) {{
                background-color: rgba(128, 128, 128, 0.03);
            }}
            .roster-table .roster-position {{
                color: #808495;
                font-weight: 600;
                width: 28%;
            }}
            .roster-table .player-position {{
                color: #808495;
                font-size: 0.78rem;
                margin-left: 0.5rem;
            }}
        </style>
        <table class="roster-table">
            <thead>
                <tr><th>Position</th><th>Player</th></tr>
            </thead>
            <tbody>{table_rows}</tbody>
        </table>
        """),
        unsafe_allow_html=True,
    )


# Restore the selected user and API client across page navigation.
if "client" not in st.session_state:
    client = SleeperClient()
else:
    client = st.session_state.get("client")

user_id = st.query_params.get("user_id")

if user_id is not None:
    st.session_state["user_id"] = str(user_id)
else:
    user_id = st.session_state["user_id"]

if user_id is None:
    st.warning("Select a user first.")
    st.switch_page("pages/leagues.py")

st.title("Team Page")

# Load the selected team's league, member, and roster records.
rosters = client.get_all_rosters(st.session_state.get("league_id"))
teams = client.get_all_users(st.session_state.get("league_id"))
league = client.get_single_league(st.session_state.get("league_id"))
team_roster = None
team_selected = None

for roster in rosters.rosters:
    if roster.user_id == user_id:
        team_roster = roster
for team in teams.users:
    if team.user_id == user_id:
        team_selected = team

if league.status == "pre_draft" or team_roster is None or team_selected is None:
    st.warning("No roster found for this user.")
    st.session_state.pop("user_id")
    st.query_params.pop("user_id")
    st.switch_page("pages/overview.py")

# Present the team identity above its roster.
team_icon, team_identity = st.columns([1, 5], vertical_alignment="center")
with team_icon:
    st.image(client.get_avatar(team_selected.avatar_id), width=112)
with team_identity:
    st.subheader(team_selected.display_team_name)
    st.caption(f"Owner: {team_selected.display_name}")

st.subheader("Roster")

# Resolve roster IDs through the cached player JSON and render the final table.
with NFL_PLAYERS_PATH.open(encoding="utf-8") as f:
    data = json.load(f)

render_roster_table(build_roster_rows(league, team_roster, data))

# Keep team, league, and account navigation anchored below the roster.
with st.bottom:
    team_change = st.button("Different Team")
    league_change = st.button("Switch Leagues")
    reset = st.button("Log Out")

if team_change:
    st.session_state.pop("user_id")
    st.query_params.pop("user_id")
    st.switch_page("pages/overview.py")
if league_change:
    st.session_state.pop("league_id")
    st.switch_page("pages/leagues.py")
if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

import streamlit as st
from fantasy_dashboard.clients.sleeper import SleeperClient
import json

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
st.write(f"Team: {team_selected.display_team_name}")
st.write(f"Owner: {team_selected.display_name}")

if league.status == "pre_draft":
    st.warning("No roster found for this user.")
    st.session_state.pop("user_id")
    st.query_params.pop("user_id")
    st.switch_page("pages/overview.py")

with open("nfl_players.json", "r") as f:
    data = json.load(f)

for starter in team_roster.starters:
    player = data[starter]
    name = f"{player['first_name']} {player['last_name']}"
    st.write(name)

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

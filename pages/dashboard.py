import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient

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

st.title("Dashboard")
league = client.get_single_league(league_id)
st.write(f"League: {league.name}")
st.write("Players: ")
teams = client.get_all_users(league_id)
players_list = []
images_list = []
for team in teams.users:
    display_name = team.display_name
    team_name = team.team_name
    if team_name == "None":
        continue
    image = client.get_avatar(team.avatar_id)
    st.write(team_name)
    st.image(image, caption=display_name)
    st.page_link("pages/team.py", label="View Team", query_params={"user_id": team.user_id})

with st.bottom:
    league_change = st.button("Switch Leagues")
    reset = st.button("Log Out")

if league_change:
    st.session_state.pop("league_id")
    st.query_params.pop("league_id")
    st.switch_page("pages/leagues.py")
if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

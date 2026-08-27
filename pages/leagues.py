import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient

if "client" not in st.session_state:
    client = SleeperClient()
else:
    client = st.session_state.get("client")

assert "sleeper_user" in st.session_state, "No user found for leagues to show"
user = st.session_state["sleeper_user"]
user_id = user.user_id

st.title("Leagues")
st.caption("Select a league to view.")
leagues = client.get_leagues(user_id, "2026", "nfl")
for league in leagues.leagues:
    st.page_link(
        "pages/overview.py",
        label=f"**{league.name}**",
        icon="🏈",
        query_params={"league_id": league.league_id},
        width="stretch",
    )

with st.bottom:
    reset = st.button("Log Out")

if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

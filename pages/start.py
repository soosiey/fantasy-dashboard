import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient

if "client" not in st.session_state:
    client = SleeperClient()
else:
    client = st.session_state.get("client")

st.title("Fantasy Football Dashboard")
st.write("Enter your Sleeper username to start")

with st.form("sleeper username"):
    username = st.text_input("Username")
    submit_button = st.form_submit_button("Continue")

if submit_button:
    user = client.get_user(username.strip())

    if user is None:
        st.error("Sleeper username not found.")
        st.stop()

    st.session_state["sleeper_user"] = user
    st.session_state["client"] = client
    st.rerun()

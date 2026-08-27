import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient

# Reuse the authenticated client when returning to the login page.
if "client" not in st.session_state:
    client = SleeperClient()
else:
    client = st.session_state.get("client")

st.title("Fantasy Football Dashboard")
st.write("Enter your Sleeper username to start")

# Collect the Sleeper username in a single-submit login form.
with st.form("sleeper username"):
    username = st.text_input("Username")
    submit_button = st.form_submit_button("Continue")

# Validate the account and establish the session used by later pages.
if submit_button:
    user = client.get_user(username.strip())

    if user is None:
        st.error("Sleeper username not found.")
        st.stop()

    st.session_state["sleeper_user"] = user
    st.session_state["client"] = client
    st.rerun()

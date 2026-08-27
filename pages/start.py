import streamlit as st

from fantasy_dashboard.data import get_user

st.title("Fantasy Football Dashboard")
st.write("Enter your Sleeper username to start")

# Collect the Sleeper username in a single-submit login form.
with st.form("sleeper username"):
    username = st.text_input("Username")
    submit_button = st.form_submit_button("Continue")

# Validate the account and establish the session used by later pages.
if submit_button:
    user = get_user(username.strip())

    if user is None:
        st.error("Sleeper username not found.")
        st.stop()

    st.session_state["sleeper_user"] = user
    st.rerun()

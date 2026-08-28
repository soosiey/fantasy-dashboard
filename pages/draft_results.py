import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.draft_table import render_draft_table
from fantasy_dashboard.data import (
    clear_draft_data,
    get_data_update,
    get_draft_picks,
    get_league,
    get_league_users,
    get_nfl_players,
)
from fantasy_dashboard.draft import build_draft_result_rows
from fantasy_dashboard.routing import (
    require_authentication,
    resolve_league_id,
    sync_query_params,
)

# Resolve league context consistently across direct links and page navigation.
require_authentication("draft-results")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

league = get_league(league_id)
draft_id = league.draft_id if league is not None else ""

# Keep the manual refresh compact and aligned with the page heading.
title_column, refresh_column = st.columns([8, 1], vertical_alignment="center")
with title_column:
    st.title("Draft Results")
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-draft-results",
        help="Reload draft results from Sleeper",
        width="content",
    )

if not draft_id or draft_id == "None":
    st.info("This league does not have a draft associated with it.")
else:
    if force_refresh:
        clear_draft_data(draft_id)
        st.rerun()

    try:
        draft = get_draft_picks(draft_id)
        league_users = get_league_users(league_id)
    except (requests.RequestException, TypeError, ValueError) as error:
        st.warning(f"Draft results could not be loaded: {error}")
    else:
        display_names_by_user_id = (
            {user.user_id: user.display_name for user in league_users.users}
            if league_users is not None
            else {}
        )

        # Filter picks by player name or the stable ID of the drafting user.
        search_column, drafter_column = st.columns(2)
        with search_column:
            player_search = st.text_input(
                "Player name",
                placeholder="Search by player name",
                value=str(st.query_params.get("search") or ""),
                key=f"draft-player-search-{league_id}",
            )
        with drafter_column:
            drafter_ids = sorted(
                {pick.picked_by for pick in draft.picks if pick.picked_by},
                key=lambda user_id: display_names_by_user_id.get(
                    user_id, user_id
                ).casefold(),
            )
            selected_drafter_id = st.selectbox(
                "Drafted by",
                ["", *drafter_ids],
                index=(
                    ["", *drafter_ids].index(str(st.query_params.get("drafter") or ""))
                    if str(st.query_params.get("drafter") or "") in ["", *drafter_ids]
                    else 0
                ),
                format_func=lambda user_id: (
                    "All users"
                    if not user_id
                    else display_names_by_user_id.get(
                        user_id, f"Unknown User ({user_id})"
                    )
                ),
                key=f"draft-drafter-{league_id}",
            )

        sync_query_params(
            league_id=league_id,
            search=player_search.strip() or None,
            drafter=selected_drafter_id or None,
        )

        rows = build_draft_result_rows(
            draft.picks,
            get_nfl_players(),
            display_names_by_user_id,
            player_search,
            selected_drafter_id,
        )
        st.caption(f"{len(rows):,} of {len(draft.picks):,} picks shown")
        if rows:
            render_draft_table(rows)
        elif draft.picks:
            st.info("No drafted players match that search.")
        else:
            st.info("No draft picks are available yet.")

        render_data_disclaimer(get_data_update("draft_picks", draft_id))

# Keep league and account navigation available below the draft results.
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

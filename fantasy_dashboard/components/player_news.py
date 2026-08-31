from datetime import datetime

import requests
import streamlit as st

from fantasy_dashboard.clients.rotoworld import RotoworldClient
from fantasy_dashboard.models.news import PlayerNewsModel
from fantasy_dashboard.models.player import PlayerModel


# Cache scraped updates briefly so reopening a player does not hammer NBC Sports.
@st.cache_data(ttl=900, show_spinner=False)
def _get_recent_news_v4(rotoworld_id: int, player_name: str) -> list[PlayerNewsModel]:
    return RotoworldClient().get_recent_news(rotoworld_id, player_name)


# Format NBC's ISO timestamp into a concise date for the news listing.
def _format_news_date(news_date: str) -> str:
    if not news_date:
        return "Date unavailable"
    try:
        return datetime.fromisoformat(news_date.replace("Z", "+00:00")).strftime(
            "%B %d, %Y"
        )
    except ValueError:
        return news_date


# Render the same player-specific news feed in dialogs and full pages.
def render_player_news(player: PlayerModel) -> None:
    player_name = f"{player.first_name} {player.last_name}".strip()
    st.caption(player_name)

    try:
        with st.spinner("Loading recent news..."):
            news_items = _get_recent_news_v4(player.rotoworld_id, player_name)
    except requests.RequestException:
        st.error("Recent news could not be loaded right now. Please try again.")
        return

    if not news_items:
        st.info("No recent Rotoworld news was found for this player.")
        return

    # Link to each report's source without reproducing the article analysis.
    with st.container(height=500, border=False):
        for index, news in enumerate(news_items):
            st.subheader(news.title)
            publication = _format_news_date(news.date)
            if news.author:
                publication = f"{publication} · By {news.author}"
            st.caption(publication)
            st.link_button("View on Rotoworld", news.source_url)
            if index < len(news_items) - 1:
                st.divider()


# Show the requested update in a modal with Streamlit's built-in close button.
@st.dialog("Recent Player News")
def show_player_news(player: PlayerModel) -> None:
    render_player_news(player)

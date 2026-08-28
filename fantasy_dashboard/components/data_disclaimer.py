from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from fantasy_dashboard.data import DataUpdate


# Format provider-fetch times in the user's application timezone.
def _format_update_time(updated_at: datetime) -> str:
    local_time = updated_at.astimezone(ZoneInfo("America/New_York"))
    return local_time.strftime("%B %d, %Y at %I:%M:%S %p %Z").replace(" 0", " ")


# Render a small data-provenance footer for every successful provider source.
def render_data_disclaimer(*updates: DataUpdate | None) -> None:
    available_updates = [update for update in updates if update is not None]
    if not available_updates:
        return

    # Keep only the newest timestamp for repeated references to one provider.
    updates_by_provider: dict[str, DataUpdate] = {}
    for update in available_updates:
        current = updates_by_provider.get(update.provider)
        if current is None or update.updated_at > current.updated_at:
            updates_by_provider[update.provider] = update

    descriptions = [
        f"{provider} data last refreshed {_format_update_time(update.updated_at)}"
        for provider, update in updates_by_provider.items()
    ]
    st.caption("Data source · " + " · ".join(descriptions))

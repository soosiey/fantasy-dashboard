from typing import Any

import requests
import streamlit as st

from fantasy_dashboard.data import (
    get_league,
    get_league_users,
    get_nfl_players,
    get_projected_player_stats,
    get_rosters,
)
from fantasy_dashboard.models.league import RosterModel
from fantasy_dashboard.player_stats import calculate_fantasy_points
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    require_authentication,
    resolve_league_id,
)
from fantasy_dashboard.trade_analysis import (
    TradeGradeWeights,
    TradeSideGrade,
    grade_hypothetical_trade,
)


def _player_name(player_id: str, players: dict[str, dict[str, Any]]) -> str:
    player = players.get(player_id, {})
    name = " ".join(
        part
        for part in (
            str(player.get("first_name") or "").strip(),
            str(player.get("last_name") or "").strip(),
        )
        if part
    )
    return name or str(player.get("full_name") or player_id)


def _player_label(
    player_id: str,
    players: dict[str, dict[str, Any]],
    projected_points: dict[str, float],
) -> str:
    position = str(players.get(player_id, {}).get("position") or "—")
    return (
        f"{_player_name(player_id, players)} · {position} · "
        f"{projected_points.get(player_id, 0.0):.1f} projected points"
    )


def _team_label(
    roster: RosterModel,
    teams_by_user_id: dict[str, Any],
) -> str:
    team = teams_by_user_id.get(roster.user_id)
    if team is None:
        return f"Roster {roster.roster_id}"
    return f"{team.display_team_name} · {team.display_name}"


def _render_grade_card(
    team_label: str,
    grade: TradeSideGrade,
    sends: list[str],
    receives: list[str],
    players: dict[str, dict[str, Any]],
) -> None:
    with st.container(border=True):
        st.subheader(team_label)
        headline_columns = st.columns(3)
        headline_columns[0].metric("Trade Grade", f"{grade.letter} · {grade.score:.1f}")
        headline_columns[1].metric("Strength", f"{grade.strength_score:.1f}")
        headline_columns[2].metric("Roster Fit", f"{grade.roster_fit_score:.1f}")

        roster_delta = grade.roster_utility_change
        st.metric(
            "Projected roster-utility change",
            f"{roster_delta:+.2f}",
            delta="Improves roster" if roster_delta > 0 else None,
        )
        movement_columns = st.columns(2)
        with movement_columns[0]:
            st.markdown("**Receives**")
            for player_id in receives:
                st.markdown(f"- {_player_name(player_id, players)}")
        with movement_columns[1]:
            st.markdown("**Sends**")
            for player_id in sends:
                st.markdown(f"- {_player_name(player_id, players)}")

        with st.expander("Score details"):
            detail_columns = st.columns(2)
            with detail_columns[0]:
                st.markdown("**Package strength**")
                st.write(
                    f"Received: {grade.received_projected_points:.2f} projected "
                    f"points · {grade.received_value_over_replacement:.2f} VOR"
                )
                st.write(
                    f"Sent: {grade.sent_projected_points:.2f} projected points · "
                    f"{grade.sent_value_over_replacement:.2f} VOR"
                )
            with detail_columns[1]:
                st.markdown("**Roster usage**")
                st.write(
                    f"Received package utilized: {grade.received_utilization:.1%}"
                )
                st.write(f"Sent package utilized: {grade.sent_utilization:.1%}")
            st.write(
                f"Roster utility: {grade.before_roster_utility:.2f} before → "
                f"{grade.after_roster_utility:.2f} after"
            )


require_authentication("trade-analysis")
league_id = resolve_league_id()
if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")
if not st.session_state.get(ANALYSIS_MODE_KEY):
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.rerun()

st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 105rem; }</style>",
    unsafe_allow_html=True,
)
st.title("Trade Analysis")
st.caption(
    "Build a two-team, player-only trade and grade what it would mean for each "
    "current roster. Nothing is submitted to Sleeper."
)

try:
    league = get_league(league_id)
    roster_container = get_rosters(league_id)
    team_container = get_league_users(league_id)
    players = get_nfl_players()
    projected_stats = get_projected_player_stats(league.season, None)
except (OSError, requests.RequestException, TypeError, ValueError) as error:
    st.warning(f"Trade analysis inputs could not be loaded: {error}")
else:
    rosters = list(roster_container.rosters if roster_container is not None else [])
    teams_by_user_id = {
        team.user_id: team
        for team in (team_container.users if team_container is not None else [])
    }
    projected_points = {
        player_id: calculate_fantasy_points(stats, league.scoring_settings)
        for player_id, stats in projected_stats.items()
    }

    if len(rosters) < 2:
        st.info("At least two league rosters are required to simulate a trade.")
    else:
        roster_by_id = {roster.roster_id: roster for roster in rosters}
        roster_ids = list(roster_by_id)
        team_columns = st.columns(2)
        with team_columns[0]:
            first_roster_id = st.selectbox(
                "First team",
                roster_ids,
                format_func=lambda roster_id: _team_label(
                    roster_by_id[roster_id], teams_by_user_id
                ),
                key=f"trade-analysis-first-team-{league_id}",
            )
        second_roster_options = [
            roster_id for roster_id in roster_ids if roster_id != first_roster_id
        ]
        with team_columns[1]:
            second_roster_id = st.selectbox(
                "Second team",
                second_roster_options,
                format_func=lambda roster_id: _team_label(
                    roster_by_id[roster_id], teams_by_user_id
                ),
                key=f"trade-analysis-second-team-{league_id}-{first_roster_id}",
            )

        first_roster = roster_by_id[first_roster_id]
        second_roster = roster_by_id[second_roster_id]
        player_columns = st.columns(2)
        with player_columns[0]:
            first_sends = st.multiselect(
                f"{_team_label(first_roster, teams_by_user_id)} sends",
                first_roster.players,
                format_func=lambda player_id: _player_label(
                    str(player_id), players, projected_points
                ),
                key=f"trade-analysis-first-players-{league_id}-{first_roster_id}",
            )
        with player_columns[1]:
            second_sends = st.multiselect(
                f"{_team_label(second_roster, teams_by_user_id)} sends",
                second_roster.players,
                format_func=lambda player_id: _player_label(
                    str(player_id), players, projected_points
                ),
                key=f"trade-analysis-second-players-{league_id}-{second_roster_id}",
            )

        with st.expander("Trade score weights"):
            weight_columns = st.columns(3)
            with weight_columns[0]:
                strength_weight = st.slider(
                    "Package strength",
                    0,
                    100,
                    50,
                    key=f"trade-analysis-strength-{league_id}",
                )
            with weight_columns[1]:
                roster_fit_weight = st.slider(
                    "Roster fit",
                    0,
                    100,
                    50,
                    key=f"trade-analysis-fit-{league_id}",
                )
            with weight_columns[2]:
                bench_depth_weight = st.slider(
                    "Bench-depth value",
                    0,
                    100,
                    35,
                    key=f"trade-analysis-bench-{league_id}",
                )

        if not first_sends or not second_sends:
            st.info("Select at least one player from each team to simulate the trade.")
        else:
            grade = grade_hypothetical_trade(
                league,
                first_roster.players,
                second_roster.players,
                [str(player_id) for player_id in first_sends],
                [str(player_id) for player_id in second_sends],
                players,
                projected_stats,
                TradeGradeWeights(
                    strength=float(strength_weight),
                    roster_fit=float(roster_fit_weight),
                    bench_depth=bench_depth_weight / 100,
                ),
            )
            result_columns = st.columns(2)
            with result_columns[0]:
                _render_grade_card(
                    _team_label(first_roster, teams_by_user_id),
                    grade.first,
                    [str(player_id) for player_id in first_sends],
                    [str(player_id) for player_id in second_sends],
                    players,
                )
            with result_columns[1]:
                _render_grade_card(
                    _team_label(second_roster, teams_by_user_id),
                    grade.second,
                    [str(player_id) for player_id in second_sends],
                    [str(player_id) for player_id in first_sends],
                    players,
                )

    with st.expander("How trade grades work"):
        st.markdown(
            r"""
            **Package strength** uses projected value over replacement (VOR), so
            positions are compared on league-specific scarcity rather than raw points.

            $$
            S_{\mathrm{strength}}
            =75+25\left(
            \frac{V_{\mathrm{received}}-V_{\mathrm{sent}}}
            {V_{\mathrm{received}}+V_{\mathrm{sent}}}
            \right)
            $$

            **Roster fit** optimizes each legal starting lineup before and after the
            trade, including FLEX and SUPER_FLEX eligibility. Bench value receives
            diminishing credit. For each package, utilization is the marginal roster
            utility divided by its VOR:

            $$
            S_{\mathrm{fit}}
            =75+25\left(
            \rho_{\mathrm{received}}-\rho_{\mathrm{sent}}
            \right)
            $$

            The final score is the weighted average of these components. A balanced,
            neutral trade centers on 75 (C). Both teams can score above 75 when they
            exchange redundant depth for players that better fit their starting needs.
            If both packages have zero value over replacement, package strength is
            treated as neutral.

            Grades use the current roster and currently available season projections.
            They do not model draft picks, keeper cost, injuries, future schedule,
            correlation between players, or uncertainty around the projections.
            """
        )

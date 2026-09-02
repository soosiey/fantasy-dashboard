from collections import Counter
from html import escape
from typing import Any
from urllib.parse import quote

import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.draft_grading import DraftPickGrade, letter_grade
from fantasy_dashboard.league_predictions import DraftTeamProjection
from fantasy_dashboard.models.draft import DraftPickModel
from fantasy_dashboard.models.user import SleeperTeam


def _player_name(pick: DraftPickModel, player: dict[str, Any]) -> str:
    catalog_name = " ".join(
        part
        for part in (
            str(player.get("first_name") or "").strip(),
            str(player.get("last_name") or "").strip(),
        )
        if part
    )
    return catalog_name or pick.player_name or "Unknown Player"


def _team_identity(team: SleeperTeam | None) -> tuple[str, str, str]:
    if team is None:
        return "Unknown Team", "Unknown User", ""
    return team.display_team_name, team.display_name, team.avatar_id


def _render_card_summary(
    pick: DraftPickModel,
    player: dict[str, Any],
    team: SleeperTeam | None,
    grade: DraftPickGrade,
) -> str:
    player_name = _player_name(pick, player)
    fantasy_team, username, avatar_id = _team_identity(team)
    avatar = (
        f'<img class="draft-grade-avatar" src="{SleeperClient.AVATAR_URL}/'
        f'{quote(avatar_id, safe="")}" alt="{escape(fantasy_team)} avatar">'
        if avatar_id and avatar_id != "None"
        else '<span class="draft-grade-avatar draft-grade-avatar-fallback">🏈</span>'
    )
    position = str(player.get("position") or "—")
    nfl_team = str(player.get("team") or "FA")
    pick_context = f"Pick {pick.pick_number}"
    if pick.amount is not None:
        pick_context += f" · ${pick.amount:,.0f}"
    elif pick.round_number:
        pick_context += f" · Round {pick.round_number}"

    return (
        '<div class="draft-grade-team">'
        f"{avatar}<div>"
        f'<div class="draft-grade-team-name">{escape(fantasy_team)}</div>'
        f'<div class="draft-grade-owner">{escape(username)}</div>'
        "</div></div>"
        '<div class="draft-grade-main">'
        '<div class="draft-grade-player">'
        f'<div class="draft-grade-player-name">{escape(player_name)}</div>'
        f'<div class="draft-grade-player-meta">{escape(position)} · '
        f"{escape(nfl_team)}</div>"
        f'<div class="draft-grade-pick">{escape(pick_context)}</div>'
        "</div>"
        f'<div class="draft-grade-mark draft-grade-{grade.letter.casefold()}">'
        f"<strong>{grade.letter}</strong>"
        f"<small>{grade.score:.1f}</small><span>Grade</span></div>"
        "</div>"
    )


def _render_pick_insight(grade: DraftPickGrade) -> str:
    auction_insight = ""
    if (
        grade.cost_score is not None
        and grade.fair_value is not None
        and grade.amount_paid is not None
    ):
        auction_insight = (
            "<br><br>"
            f"<strong>Cost efficiency · {grade.cost_score:.1f}/100</strong><br>"
            f"${grade.amount_paid:,.0f} paid versus a ${grade.fair_value:,.2f} "
            "fair value immediately before the winning bid."
        )
    return (
        '<div class="draft-grade-insight">'
        f"<strong>Positional strength · {grade.strength_score:.1f}/100</strong><br>"
        f"{grade.projected_points:.2f} projected points versus a "
        f"{grade.position_average:.2f} positional average.<br><br>"
        f"<strong>Roster value · {grade.roster_fit_score:.1f}/100</strong><br>"
        f"{grade.marginal_roster_value:.2f} marginal value versus "
        f"{grade.best_available_roster_value:.2f} for the best available choice; "
        f"the position's wait cost was {grade.wait_cost:.2f}."
        f"{auction_insight}"
        "</div>"
    )


def _toggle_insight(insight_key: str) -> None:
    st.session_state[insight_key] = not bool(st.session_state.get(insight_key))


def _render_card_styles() -> None:
    st.markdown(
        """
        <style>
            [class*="st-key-draft-grade-card-"] {
                background: rgba(128, 128, 128, 0.055);
                border: 1px solid rgba(128, 128, 128, 0.22);
                border-radius: 0.8rem;
                min-height: 17rem;
                padding: 1rem;
            }
            .draft-grade-team {
                align-items: center;
                display: flex;
                gap: 0.65rem;
            }
            .draft-grade-avatar {
                align-items: center;
                border-radius: 50%;
                display: flex;
                height: 2.75rem;
                justify-content: center;
                object-fit: cover;
                width: 2.75rem;
            }
            .draft-grade-avatar-fallback {
                background: rgba(128, 128, 128, 0.12);
            }
            .draft-grade-team-name,
            .draft-grade-player-name {
                font-weight: 700;
            }
            .draft-grade-owner {
                color: #808495;
                font-size: 0.72rem;
                margin-top: 0.05rem;
            }
            .draft-grade-main {
                align-items: center;
                display: flex;
                justify-content: space-between;
                margin: 1.5rem 0 1rem;
            }
            .draft-grade-player-name {
                font-size: 1.05rem;
            }
            .draft-grade-player-meta,
            .draft-grade-pick {
                color: #808495;
                font-size: 0.78rem;
                margin-top: 0.2rem;
            }
            .draft-grade-mark {
                align-items: center;
                border: 1px solid currentColor;
                border-radius: 0.65rem;
                display: flex;
                flex-direction: column;
                min-width: 3.4rem;
                padding: 0.35rem 0.55rem;
            }
            .draft-grade-a { background: rgba(34, 197, 94, 0.13); color: #16a34a; }
            .draft-grade-b { background: rgba(59, 130, 246, 0.13); color: #2563eb; }
            .draft-grade-c { background: rgba(234, 179, 8, 0.13); color: #ca8a04; }
            .draft-grade-d { background: rgba(249, 115, 22, 0.13); color: #ea580c; }
            .draft-grade-f { background: rgba(239, 68, 68, 0.13); color: #dc2626; }
            .draft-grade-mark strong {
                font-size: 1.65rem;
                line-height: 1.1;
            }
            .draft-grade-mark span {
                font-size: 0.62rem;
                font-weight: 700;
                text-transform: uppercase;
            }
            .draft-grade-mark small {
                font-size: 0.68rem;
                font-weight: 700;
            }
            .draft-grade-insight {
                background: rgba(59, 130, 246, 0.08);
                border-radius: 0.45rem;
                color: #808495;
                font-size: 0.78rem;
                margin-top: 0.6rem;
                padding: 0.65rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_draft_grade_cards(
    picks: list[DraftPickModel],
    players: dict[str, dict[str, Any]],
    teams: list[SleeperTeam],
    league_id: str,
    grades: dict[int, DraftPickGrade],
) -> None:
    if not picks:
        st.info("No draft picks are available to grade yet.")
        return

    _render_card_styles()
    teams_by_user_id = {team.user_id: team for team in teams}
    for row_start in range(0, len(picks), 3):
        columns = st.columns(3)
        for column, pick in zip(columns, picks[row_start : row_start + 3]):
            player = players.get(pick.player_id) or {}
            team = teams_by_user_id.get(pick.picked_by)
            grade = grades[pick.pick_number]
            insight_key = (
                f"draft-grade-insight-{league_id}-{pick.pick_number}-{pick.player_id}"
            )
            with column, st.container(
                key=f"draft-grade-card-{pick.pick_number}-{pick.player_id}"
            ):
                st.markdown(
                    _render_card_summary(pick, player, team, grade),
                    unsafe_allow_html=True,
                )
                if st.session_state.get(insight_key):
                    st.markdown(
                        _render_pick_insight(grade),
                        unsafe_allow_html=True,
                    )
                st.button(
                    "View",
                    key=f"view-draft-grade-{league_id}-{pick.pick_number}",
                    width="stretch",
                    on_click=_toggle_insight,
                    args=(insight_key,),
                )


def _render_overall_summary(
    team: SleeperTeam,
    picks: list[DraftPickModel],
    players: dict[str, dict[str, Any]],
    projection: DraftTeamProjection,
) -> str:
    fantasy_team, username, avatar_id = _team_identity(team)
    avatar = (
        f'<img class="draft-grade-avatar" src="{SleeperClient.AVATAR_URL}/'
        f'{quote(avatar_id, safe="")}" alt="{escape(fantasy_team)} avatar">'
        if avatar_id and avatar_id != "None"
        else '<span class="draft-grade-avatar draft-grade-avatar-fallback">🏈</span>'
    )
    position_counts = Counter(
        str((players.get(pick.player_id) or {}).get("position") or "Other")
        for pick in picks
    )
    position_summary = " · ".join(
        f"{position} {count}" for position, count in sorted(position_counts.items())
    )
    if not position_summary:
        position_summary = "No selections recorded"
    total_spent = sum(pick.amount or 0 for pick in picks)
    draft_context = (
        f"${total_spent:,.0f} total spent"
        if any(pick.amount is not None for pick in picks)
        else f"{len(picks)} rounds represented"
    )
    pick_label = "pick" if len(picks) == 1 else "picks"
    grade_score = projection.championship_grade_score
    grade_letter = letter_grade(grade_score)

    return (
        '<div class="draft-grade-team">'
        f"{avatar}<div>"
        f'<div class="draft-grade-team-name">{escape(fantasy_team)}</div>'
        f'<div class="draft-grade-owner">{escape(username)}</div>'
        "</div></div>"
        '<div class="draft-grade-main">'
        '<div class="draft-grade-player">'
        f'<div class="draft-grade-player-name">{len(picks)} draft {pick_label}</div>'
        f'<div class="draft-grade-player-meta">{escape(position_summary)}</div>'
        f'<div class="draft-grade-pick">{escape(draft_context)} · '
        f"{projection.championship_probability:.1%} title odds</div>"
        "</div>"
        f'<div class="draft-grade-mark draft-grade-{grade_letter.casefold()}">'
        f"<strong>{grade_letter}</strong>"
        f"<small>{grade_score:.1f}</small><span>Grade</span></div>"
        "</div>"
    )


def render_overall_draft_grade_cards(
    picks: list[DraftPickModel],
    players: dict[str, dict[str, Any]],
    teams: list[SleeperTeam],
    league_id: str,
    projections: dict[str, DraftTeamProjection],
) -> None:
    picks_by_user_id: dict[str, list[DraftPickModel]] = {}
    for pick in picks:
        picks_by_user_id.setdefault(pick.picked_by, []).append(pick)
    drafting_teams = [
        team
        for team in teams
        if picks_by_user_id.get(team.user_id) and team.user_id in projections
    ]
    if not drafting_teams:
        st.info("No fantasy teams with draft picks are available to grade yet.")
        return

    _render_card_styles()

    for row_start in range(0, len(drafting_teams), 3):
        columns = st.columns(3)
        for column, team in zip(columns, drafting_teams[row_start : row_start + 3]):
            team_picks = picks_by_user_id.get(team.user_id, [])
            projection = projections[team.user_id]
            insight_key = f"overall-draft-grade-insight-{league_id}-{team.user_id}"
            with column, st.container(key=f"draft-grade-card-overall-{team.user_id}"):
                st.markdown(
                    _render_overall_summary(team, team_picks, players, projection),
                    unsafe_allow_html=True,
                )
                if st.session_state.get(insight_key):
                    st.markdown(
                        '<div class="draft-grade-insight">'
                        f"<strong>Championship probability · "
                        f"{projection.championship_probability:.1%}</strong><br>"
                        f"Playoff probability: {projection.playoff_probability:.1%}. "
                        f"Average one-week win probability against league opponents: "
                        f"{projection.average_weekly_win_probability:.1%}.<br><br>"
                        f"The projected best lineup averages {projection.weekly_mean:.2f} "
                        f"points with a {projection.weekly_standard_deviation:.2f}-point "
                        f"weekly standard deviation. Championship odds are normalized "
                        f"against an equal-share championship baseline for a score of "
                        f"{projection.championship_grade_score:.1f}/100, giving "
                        f"{escape(team.display_team_name)} an overall "
                        f"{letter_grade(projection.championship_grade_score)} grade."
                        "</div>",
                        unsafe_allow_html=True,
                    )
                st.button(
                    "View",
                    key=f"view-overall-draft-grade-{league_id}-{team.user_id}",
                    width="stretch",
                    on_click=_toggle_insight,
                    args=(insight_key,),
                )

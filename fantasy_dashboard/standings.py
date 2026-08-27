from dataclasses import dataclass

from fantasy_dashboard.models.league import RosterModel
from fantasy_dashboard.models.user import SleeperTeam


# Represent one display-ready row in the ranked league standings.
@dataclass(frozen=True, slots=True)
class StandingRow:
    placement: int
    team_name: str
    display_name: str
    avatar_id: str
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float


# Join roster results to league users and apply the configured tiebreakers.
def build_standings(
    rosters: list[RosterModel], teams: list[SleeperTeam]
) -> list[StandingRow]:
    teams_by_user_id = {team.user_id: team for team in teams}
    ranked_rosters = [
        roster for roster in rosters if roster.user_id in teams_by_user_id
    ]
    ranked_rosters.sort(
        key=lambda roster: (
            -roster.wins,
            -roster.points,
            -roster.points_against,
        )
    )

    # Assign sequential placements after all record and points tiebreakers.
    return [
        StandingRow(
            placement=placement,
            team_name=teams_by_user_id[roster.user_id].display_team_name,
            display_name=teams_by_user_id[roster.user_id].display_name,
            avatar_id=teams_by_user_id[roster.user_id].avatar_id,
            wins=roster.wins,
            losses=roster.losses,
            ties=roster.ties,
            points_for=roster.points,
            points_against=roster.points_against,
        )
        for placement, roster in enumerate(ranked_rosters, start=1)
    ]

from dataclasses import dataclass

from fantasy_dashboard.models.bracket import BracketMatchup, BracketSource
from fantasy_dashboard.models.league import RosterModel
from fantasy_dashboard.models.user import SleeperTeam
from fantasy_dashboard.standings import rank_rosters


# Store one resolved or pending team slot in a displayed playoff matchup.
@dataclass(frozen=True, slots=True)
class PlayoffSlot:
    label: str
    roster_id: int | None
    is_winner: bool
    seed: int | None = None
    score: float | None = None


# Store the presentation values needed for one bracket matchup card.
@dataclass(frozen=True, slots=True)
class PlayoffMatchup:
    matchup_id: int
    title: str
    team_1: PlayoffSlot
    team_2: PlayoffSlot


# Add explicit opening-round cards for teams Sleeper advances with a bye.
def _add_opening_round_byes(
    rounds: dict[int, list[PlayoffMatchup]],
    matchups: list[BracketMatchup],
    team_names_by_roster_id: dict[int, str],
    seeds_by_roster_id: dict[int, int],
) -> None:
    round_numbers = sorted(rounds)
    if len(round_numbers) < 2:
        return

    opening_round, following_round = round_numbers[:2]
    opening_matchups = {
        matchup.matchup_id: matchup
        for matchup in matchups
        if matchup.round == opening_round
    }
    opening_views = {matchup.matchup_id: matchup for matchup in rounds[opening_round]}
    opening_roster_ids = {
        roster_id
        for matchup in opening_matchups.values()
        for roster_id in (matchup.team_1_roster_id, matchup.team_2_roster_id)
        if roster_id is not None
    }
    ordered_opening_matchups: list[PlayoffMatchup] = []
    displayed_matchup_ids: set[int] = set()
    displayed_bye_roster_ids: set[int] = set()

    # Follow the next round's slots so each bye sits beside its feeder matchup.
    for matchup in sorted(
        (item for item in matchups if item.round == following_round),
        key=lambda item: item.matchup_id,
    ):
        slots = (
            (matchup.team_1_roster_id, matchup.team_1_from),
            (matchup.team_2_roster_id, matchup.team_2_from),
        )
        for roster_id, source in slots:
            if (
                roster_id is not None
                and roster_id not in opening_roster_ids
                and roster_id not in displayed_bye_roster_ids
            ):
                ordered_opening_matchups.append(
                    PlayoffMatchup(
                        matchup_id=-roster_id,
                        title="First-round bye",
                        team_1=PlayoffSlot(
                            label=team_names_by_roster_id.get(
                                roster_id, f"Roster {roster_id}"
                            ),
                            roster_id=roster_id,
                            is_winner=False,
                            seed=seeds_by_roster_id.get(roster_id),
                        ),
                        team_2=PlayoffSlot(
                            label="Bye week",
                            roster_id=None,
                            is_winner=False,
                        ),
                    )
                )
                displayed_bye_roster_ids.add(roster_id)
            elif (
                source is not None
                and source.matchup_id in opening_views
                and source.matchup_id not in displayed_matchup_ids
            ):
                ordered_opening_matchups.append(opening_views[source.matchup_id])
                displayed_matchup_ids.add(source.matchup_id)

    # Retain any opening matchups not referenced by the following round.
    ordered_opening_matchups.extend(
        matchup
        for matchup_id, matchup in opening_views.items()
        if matchup_id not in displayed_matchup_ids
    )
    rounds[opening_round] = ordered_opening_matchups


# Resolve direct roster IDs and winner/loser references into readable slots.
def _resolve_slot(
    roster_id: int | None,
    source: BracketSource | None,
    winner_roster_id: int | None,
    matchups_by_id: dict[int, BracketMatchup],
    team_names_by_roster_id: dict[int, str],
    seeds_by_roster_id: dict[int, int],
) -> PlayoffSlot:
    resolved_roster_id = roster_id
    if resolved_roster_id is None and source is not None:
        source_matchup = matchups_by_id.get(source.matchup_id)
        if source_matchup is not None:
            resolved_roster_id = (
                source_matchup.winner_roster_id
                if source.outcome == "winner"
                else source_matchup.loser_roster_id
            )

    if resolved_roster_id is not None:
        return PlayoffSlot(
            label=team_names_by_roster_id.get(
                resolved_roster_id, f"Roster {resolved_roster_id}"
            ),
            roster_id=resolved_roster_id,
            is_winner=resolved_roster_id == winner_roster_id,
            seed=seeds_by_roster_id.get(resolved_roster_id),
        )
    if source is not None:
        return PlayoffSlot(
            label=f"{source.outcome.title()} of Match {source.matchup_id}",
            roster_id=None,
            is_winner=False,
        )
    return PlayoffSlot(label="TBD", roster_id=None, is_winner=False)


# Join bracket roster IDs to team names and group matchups from left to right.
def build_playoff_rounds(
    matchups: list[BracketMatchup],
    rosters: list[RosterModel],
    teams: list[SleeperTeam],
) -> dict[int, list[PlayoffMatchup]]:
    teams_by_user_id = {team.user_id: team for team in teams}
    team_names_by_roster_id = {
        roster.roster_id: teams_by_user_id[roster.user_id].display_team_name
        for roster in rosters
        if roster.user_id in teams_by_user_id
    }
    matchups_by_id = {matchup.matchup_id: matchup for matchup in matchups}
    seeds_by_roster_id = {
        roster.roster_id: seed
        for seed, roster in enumerate(rank_rosters(rosters), start=1)
    }
    placement_titles = {1: "Championship", 3: "Third Place", 5: "Fifth Place"}
    rounds: dict[int, list[PlayoffMatchup]] = {}

    for matchup in sorted(matchups, key=lambda item: (item.round, item.matchup_id)):
        matchup_view = PlayoffMatchup(
            matchup_id=matchup.matchup_id,
            title=placement_titles.get(
                matchup.placement, f"Match {matchup.matchup_id}"
            ),
            team_1=_resolve_slot(
                matchup.team_1_roster_id,
                matchup.team_1_from,
                matchup.winner_roster_id,
                matchups_by_id,
                team_names_by_roster_id,
                seeds_by_roster_id,
            ),
            team_2=_resolve_slot(
                matchup.team_2_roster_id,
                matchup.team_2_from,
                matchup.winner_roster_id,
                matchups_by_id,
                team_names_by_roster_id,
                seeds_by_roster_id,
            ),
        )
        rounds.setdefault(matchup.round, []).append(matchup_view)

    _add_opening_round_byes(
        rounds,
        matchups,
        team_names_by_roster_id,
        seeds_by_roster_id,
    )
    return rounds

from fantasy_dashboard.league_predictions import (
    build_optimized_week_matchups,
    optimize_lineup,
    project_playoffs,
    project_regular_season,
)
from fantasy_dashboard.models.league import LeagueModel, RosterModel
from fantasy_dashboard.models.matchup import WeeklyMatchupModel
from fantasy_dashboard.models.user import SleeperTeam


def _league(roster_positions: list[str], playoff_teams: int = 2) -> LeagueModel:
    return LeagueModel.from_api(
        {
            "league_id": "league-1",
            "total_rosters": playoff_teams,
            "status": "in_season",
            "sport": "nfl",
            "settings": {
                "waiver_budget": 100,
                "playoff_teams": playoff_teams,
                "num_teams": playoff_teams,
                "playoff_week_start": 15,
                "waiver_day_of_week": 2,
                "trade_deadline": 11,
                "reserve_slots": 1,
            },
            "roster_positions": roster_positions,
            "name": "Prediction League",
            "draft_id": "draft-1",
            "scoring_settings": {"pts": 1},
            "bracket_id": "winners-1",
            "loser_bracket_id": "losers-1",
            "avatar": "avatar-1",
            "season": "2026",
            "season_type": "regular",
        }
    )


def _roster(
    roster_id: int,
    player_ids: list[str],
    *,
    wins: int = 0,
    losses: int = 0,
    points: float = 0,
) -> RosterModel:
    return RosterModel(
        starters=player_ids[:1],
        wins=wins,
        waiver=roster_id,
        budget_used=0,
        moves=0,
        ties=0,
        losses=losses,
        points=points,
        points_against=0,
        roster_id=roster_id,
        reserve=[],
        players=player_ids,
        user_id=f"user-{roster_id}",
        league_id="league-1",
    )


def _players(*positions: str) -> dict[str, dict[str, object]]:
    return {
        f"player-{index}": {
            "player_id": f"player-{index}",
            "position": position,
            "fantasy_positions": [position],
        }
        for index, position in enumerate(positions, 1)
    }


def test_optimal_lineup_accounts_for_flex_assignment() -> None:
    league = _league(["RB", "FLEX", "BN"])
    roster = _roster(1, ["player-1", "player-2", "player-3"])
    players = _players("RB", "WR", "RB")

    lineup = optimize_lineup(
        roster,
        league,
        players,
        {
            "player-1": {"pts": 20},
            "player-2": {"pts": 15},
            "player-3": {"pts": 10},
        },
    )

    assert lineup.score == 35
    assert lineup.player_ids == ("player-1", "player-2")


def test_week_matchups_replace_submitted_starters_with_optimal_lineup() -> None:
    league = _league(["RB", "FLEX", "BN"])
    roster = _roster(1, ["player-3", "player-1", "player-2"])
    scheduled_matchup = WeeklyMatchupModel(
        ["player-3", "player-1"],
        roster.players,
        1,
        7,
        0,
        None,
    )

    optimized = build_optimized_week_matchups(
        league,
        [roster],
        _players("RB", "WR", "RB"),
        [scheduled_matchup],
        {
            "player-1": {"pts": 20},
            "player-2": {"pts": 15},
            "player-3": {"pts": 10},
        },
    )

    assert optimized[0].starters == ["player-1", "player-2"]
    assert optimized[0].players == roster.players
    assert optimized[0].matchup_id == 7
    assert optimized[0].points == 35


def test_optimal_lineup_fills_legal_slots_when_projections_are_missing() -> None:
    lineup = optimize_lineup(
        _roster(1, ["player-1", "player-2"]),
        _league(["QB", "SUPER_FLEX"]),
        _players("QB", "WR"),
        {},
    )

    assert lineup.score == 0
    assert set(lineup.player_ids) == {"player-1", "player-2"}


def test_remaining_schedule_updates_and_ranks_current_records() -> None:
    league = _league(["QB", "BN"])
    rosters = [
        _roster(1, ["player-1"], losses=1, points=91),
        _roster(2, ["player-2"], wins=1, points=100),
    ]
    teams = [
        SleeperTeam("user-1", "One", "", "Team One"),
        SleeperTeam("user-2", "Two", "", "Team Two"),
    ]
    matchups = [
        WeeklyMatchupModel(["player-1"], ["player-1"], 1, 1, 0, None),
        WeeklyMatchupModel(["player-2"], ["player-2"], 2, 1, 0, None),
    ]

    standings = project_regular_season(
        league,
        rosters,
        teams,
        _players("QB", "QB"),
        {2: matchups},
        {2: {"player-1": {"pts": 20}, "player-2": {"pts": 10}}},
    )

    assert [standing.team_name for standing in standings] == ["Team One", "Team Two"]
    assert [(standing.wins, standing.losses) for standing in standings] == [
        (1, 1),
        (1, 1),
    ]
    assert [standing.points_for for standing in standings] == [111, 110]


def test_playoff_projection_applies_byes_and_weekly_optimal_scores() -> None:
    league = _league(["QB", "BN"], playoff_teams=3)
    rosters = [
        _roster(1, ["player-1"]),
        _roster(2, ["player-2"]),
        _roster(3, ["player-3"]),
    ]
    teams = [
        SleeperTeam(f"user-{index}", f"User {index}", "", f"Team {index}")
        for index in range(1, 4)
    ]
    standings = project_regular_season(
        league,
        rosters,
        teams,
        _players("QB", "QB", "QB"),
        {},
        {},
    )

    projection = project_playoffs(
        league,
        rosters,
        standings,
        _players("QB", "QB", "QB"),
        {
            15: {
                "player-1": {"pts": 1},
                "player-2": {"pts": 20},
                "player-3": {"pts": 10},
            },
            16: {
                "player-1": {"pts": 30},
                "player-2": {"pts": 20},
                "player-3": {"pts": 10},
            },
        },
    )

    assert len(projection.rounds[1]) == 2
    assert projection.rounds[1][0].team_2.label == "Bye week"
    assert projection.rounds[1][0].team_1.score is None
    assert projection.champion is not None
    assert projection.champion.roster_id == 1
    assert projection.runner_up is not None
    assert projection.runner_up.roster_id == 2

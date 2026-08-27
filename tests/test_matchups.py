from types import SimpleNamespace

from fantasy_dashboard.components import matchup_board
from fantasy_dashboard.matchups import build_head_to_head_matchups
from fantasy_dashboard.models.matchup import (
    WeeklyMatchupContainer,
    WeeklyMatchupModel,
)


# Supply only the league configuration needed to arrange matchup rows.
def _league(*positions: str) -> SimpleNamespace:
    return SimpleNamespace(roster_positions=list(positions))


# Build one normalized weekly entry while allowing each test to override its data.
def _weekly_matchup(**overrides: object) -> WeeklyMatchupModel:
    data = {
        "starters": [],
        "players": [],
        "roster_id": 1,
        "matchup_id": 1,
        "points": 0,
    }
    data.update(overrides)
    return WeeklyMatchupModel.from_json(data)


# Empty Sleeper responses should remain valid empty collections.
def test_empty_matchup_response_returns_empty_container() -> None:
    container = WeeklyMatchupContainer.from_api([])

    assert container.matchups == []
    assert build_head_to_head_matchups([], _league("QB"), [], [], {}) == []


# Missing optional API fields should normalize to safe values instead of failing.
def test_empty_matchup_data_uses_defaults() -> None:
    matchup = WeeklyMatchupModel.from_json({})

    assert matchup.starters == []
    assert matchup.players == []
    assert matchup.roster_id == 0
    assert matchup.matchup_id is None
    assert matchup.displayed_points == 0
    assert matchup.players_points == {}


# Missing teams, opponents, and player records should produce display fallbacks.
def test_incomplete_matchup_builds_fallback_team_and_empty_players() -> None:
    matchup = _weekly_matchup(starters=["missing-player"])

    result = build_head_to_head_matchups(
        [matchup], _league("QB"), [], [], {}
    )

    assert len(result) == 1
    assert result[0].left_team.team_name == "Roster 1"
    assert result[0].right_team.team_name == "Bye"
    assert result[0].lineup[0].left_player.name == "Empty"
    assert result[0].lineup[0].left_player.points == 0
    assert result[0].lineup[0].right_player.name == "Empty"


# Sleeper player scores should be retained, with absent scores defaulting to zero.
def test_missing_player_score_defaults_to_zero() -> None:
    matchup = _weekly_matchup(
        starters=["scored-player"],
        players=["scored-player", "unscored-player"],
        players_points={"scored-player": 12.5},
    )
    players = {
        "scored-player": {
            "player_id": "scored-player",
            "first_name": "Scored",
            "last_name": "Player",
        },
        "unscored-player": {
            "player_id": "unscored-player",
            "first_name": "Unscored",
            "last_name": "Player",
        },
    }

    result = build_head_to_head_matchups(
        [matchup], _league("QB", "BN"), [], [], players
    )

    assert result[0].lineup[0].left_player.points == 12.5
    assert result[0].lineup[1].left_player.points == 0


# The board should give a useful empty state rather than rendering blank markup.
def test_empty_matchup_board_shows_message(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(
        matchup_board,
        "st",
        SimpleNamespace(info=messages.append),
    )

    matchup_board.render_matchup_board([])

    assert messages == ["No matchups are available for this week."]

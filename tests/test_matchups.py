from types import SimpleNamespace

from fantasy_dashboard.components import matchup_board
from fantasy_dashboard.components.matchup_board import PlayerComparisonSelection
from fantasy_dashboard.matchups import (
    MatchupPlayer,
    MatchupTeam,
    build_head_to_head_matchups,
    build_week_game_statuses,
    build_week_opponents,
)
from fantasy_dashboard.models.matchup import (
    WeeklyMatchupContainer,
    WeeklyMatchupModel,
)


# Supply only the league configuration needed to arrange matchup rows.
def _league(*positions: str) -> SimpleNamespace:
    return SimpleNamespace(
        roster_positions=list(positions),
        scoring_settings={"pass_yd": 0.04, "pass_td": 4, "rush_yd": 0.1},
    )


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

    result = build_head_to_head_matchups([matchup], _league("QB"), [], [], {})

    assert len(result) == 1
    assert result[0].left_team.team_name == "Roster 1"
    assert result[0].right_team.team_name == "Bye"
    assert result[0].lineup[0].left_player.name == "Empty"
    assert result[0].lineup[0].left_player.points is None
    assert result[0].lineup[0].right_player.name == "Empty"


# Sleeper player scores should be retained, with absent scores shown as unavailable.
def test_missing_player_score_is_unavailable() -> None:
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
    assert result[0].lineup[0].left_player.player_id == "scored-player"
    assert result[0].lineup[1].left_player.points is None


def test_empty_current_week_stats_leave_matchup_scores_unavailable() -> None:
    matchup = _weekly_matchup(starters=["starter"], players=["starter"])
    players = {
        "starter": {
            "player_id": "starter",
            "first_name": "Starting",
            "last_name": "Player",
        }
    }

    result = build_head_to_head_matchups(
        [matchup], _league("QB"), [], [], players, {}
    )

    assert result[0].lineup[0].left_player.points is None
    assert result[0].left_team.points is None
    assert "—" in matchup_board._render_player(result[0].lineup[0].left_player, "left")
    assert "—" in matchup_board._render_team_placard(result[0].left_team, "left")


# NFL stats should drive player scores and starter-only team totals.
def test_nfl_stats_score_players_and_exclude_bench_from_team_total() -> None:
    matchup = _weekly_matchup(
        starters=["starter"],
        players=["starter", "bench"],
        points=99,
    )
    players = {
        "starter": {
            "player_id": "starter",
            "first_name": "Starting",
            "last_name": "Quarterback",
            "injury_status": "Questionable",
            "active": False,
        },
        "bench": {
            "player_id": "bench",
            "first_name": "Bench",
            "last_name": "Player",
        },
    }
    stats = {
        "starter": {"pass_yd": 250, "pass_td": 1},
        "bench": {"rush_yd": 100},
    }
    players["starter"]["team"] = "KC"

    result = build_head_to_head_matchups(
        [matchup],
        _league("QB", "BN"),
        [],
        [],
        players,
        stats,
        {"KC": "vs BUF"},
        {"KC": "playing"},
    )

    assert result[0].lineup[0].left_player.points == 14
    assert result[0].lineup[0].left_player.opponent == "vs BUF"
    assert result[0].lineup[0].left_player.injury_status == "Questionable"
    assert result[0].lineup[0].left_player.game_status == "playing"
    assert result[0].lineup[0].left_player.is_inactive is True
    assert result[0].lineup[1].left_player.points == 10
    assert result[0].left_team.points == 14


def test_week_opponents_indexes_both_teams_for_selected_week() -> None:
    schedule = [
        {"week": 1, "home": "KC", "away": "BUF"},
        {"week": 2, "home": "KC", "away": "DEN"},
        {"week": 1, "home": None, "away": "NYJ"},
    ]

    assert build_week_opponents(schedule, 1) == {
        "KC": "vs BUF",
        "BUF": "at KC",
    }


# Sleeper game states should shade both teams with the matching display state.
def test_week_game_statuses_normalize_schedule_states() -> None:
    schedule = [
        {
            "week": 1,
            "home": "KC",
            "away": "BUF",
            "status": "pre_game",
        },
        {
            "week": 1,
            "home": "DAL",
            "away": "NYG",
            "status": "in_game",
        },
        {
            "week": 1,
            "home": "PHI",
            "away": "WAS",
            "status": "post_game",
        },
        {
            "week": 2,
            "home": "MIA",
            "away": "NE",
            "status": "pre_game",
        },
    ]

    assert build_week_game_statuses(schedule, 1) == {
        "KC": "to-play",
        "BUF": "to-play",
        "DAL": "playing",
        "NYG": "playing",
        "PHI": "finished",
        "WAS": "finished",
    }


# Only unplayed starters should contribute to the placard's remaining count.
def test_matchup_team_counts_to_play_starters_only() -> None:
    matchup = _weekly_matchup(
        starters=["starter"],
        players=["starter", "bench"],
    )
    players = {
        "starter": {
            "player_id": "starter",
            "first_name": "Starting",
            "team": "KC",
        },
        "bench": {
            "player_id": "bench",
            "first_name": "Bench",
            "team": "BUF",
        },
    }

    result = build_head_to_head_matchups(
        [matchup],
        _league("QB", "BN"),
        [],
        [],
        players,
        game_statuses_by_team={"KC": "to-play", "BUF": "to-play"},
    )

    assert result[0].left_team.to_play_count == 1
    assert result[0].right_team.to_play_count == 0


# Remaining counts should sit outside the mirrored owner labels.
def test_team_placard_mirrors_to_play_count_around_owner() -> None:
    team = MatchupTeam("Team", "Owner", 10, "user-1", 3)

    left_markup = matchup_board._render_team_placard(team, "left")
    right_markup = matchup_board._render_team_placard(team, "right")

    assert left_markup.index("(3)") < left_markup.index("Owner")
    assert right_markup.index("Owner") < right_markup.index("(3)")


# Empty, injured, and inactive starters should receive the warning border only.
def test_starter_attention_border_excludes_bench_players() -> None:
    empty_starter = MatchupPlayer("Empty", "")
    injured_starter = MatchupPlayer(
        "Injured Player", "KC", player_id="injured", injury_status="Out"
    )
    inactive_starter = MatchupPlayer(
        "Inactive Player", "BUF", player_id="inactive", is_inactive=True
    )

    assert "matchup-player-attention" in matchup_board._render_player(
        empty_starter, "left", True
    )
    assert "matchup-player-attention" in matchup_board._render_player(
        injured_starter, "left", True
    )
    assert "matchup-player-attention" in matchup_board._render_player(
        inactive_starter, "right", True
    )
    assert "matchup-player-attention" not in matchup_board._render_player(
        injured_starter, "left", False
    )


# The first bench row should be visually divided from the starting lineup.
def test_matchup_board_marks_bench_rows(monkeypatch) -> None:
    matchup = _weekly_matchup(
        starters=["starter"],
        players=["starter", "bench"],
    )
    players = {
        player_id: {
            "player_id": player_id,
            "first_name": player_id.title(),
            "team": "KC",
            "injury_status": ("Questionable" if player_id == "starter" else None),
        }
        for player_id in ("starter", "bench")
    }
    rendered_markup: list[str] = []
    container_keys: list[str] = []

    class FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def markdown(self, markup: str, **kwargs: object) -> None:
            rendered_markup.append(markup)

    def fake_container(*, key: str) -> FakeContext:
        container_keys.append(key)
        return FakeContext()

    result = build_head_to_head_matchups(
        [matchup],
        _league("QB", "BN"),
        [],
        [],
        players,
        game_statuses_by_team={"KC": "to-play"},
    )
    monkeypatch.setattr(
        matchup_board,
        "st",
        SimpleNamespace(
            info=lambda message: None,
            markdown=lambda markup, **kwargs: rendered_markup.append(markup),
            container=fake_container,
            columns=lambda *args, **kwargs: [
                FakeContext(),
                FakeContext(),
                FakeContext(),
            ],
            button=lambda *args, **kwargs: False,
        ),
    )

    matchup_board.render_matchup_board(result, "league 1")

    assert any("matchup-lineup-row-bench" in key for key in container_keys)
    assert "border-top" in rendered_markup[0]
    assert "matchup-player-click" in rendered_markup[0]
    assert any("matchup-position-click" in key for key in container_keys)
    assert ':has([data-testid="stButton"])' in rendered_markup[0]
    assert "transform: translateX(-50%)" in rendered_markup[0]
    assert "transform: translateY(-0.4rem)" in rendered_markup[0]
    assert "injury-questionable" in rendered_markup[0]
    assert any('title="Questionable">Q</span>' in item for item in rendered_markup)
    assert any("matchup-player-status-to-play" in item for item in rendered_markup)
    assert any("matchup-player-attention" in item for item in rendered_markup)


# Clicking a position bubble should select both players in that lineup row.
def test_position_circle_selects_player_comparison(monkeypatch) -> None:
    matchup = _weekly_matchup(
        starters=["left-player"],
        players=["left-player"],
    )
    players = {
        "left-player": {
            "player_id": "left-player",
            "first_name": "Left",
        }
    }

    class FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def markdown(self, *args: object, **kwargs: object) -> None:
            return None

    monkeypatch.setattr(
        matchup_board,
        "st",
        SimpleNamespace(
            info=lambda message: None,
            markdown=lambda *args, **kwargs: None,
            container=lambda **kwargs: FakeContext(),
            columns=lambda *args, **kwargs: [
                FakeContext(),
                FakeContext(),
                FakeContext(),
            ],
            button=lambda *args, **kwargs: str(kwargs.get("key", "")).startswith(
                "matchup-position-button-"
            ),
        ),
    )
    board = build_head_to_head_matchups([matchup], _league("QB"), [], [], players)

    selection = matchup_board.render_matchup_board(board, "league-1")

    assert selection == PlayerComparisonSelection("left-player", None)


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

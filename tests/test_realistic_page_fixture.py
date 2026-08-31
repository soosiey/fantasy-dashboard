from fantasy_dashboard import data


def test_realistic_backend_covers_positions_and_week_states(
    realistic_page_backend,
) -> None:
    del realistic_page_backend
    players = data.get_nfl_players()

    assert {player["position"] for player in players.values()} == {
        "QB",
        "RB",
        "WR",
        "TE",
        "K",
        "DEF",
    }
    assert len(data.get_player_stats("2026", "regular", 1)) == 6
    assert data.get_player_stats("2026", "regular", 2) == {}
    assert len(data.get_projected_player_stats("2026", 2)) == 6
    assert data.get_player_stats("2026", "regular", 3) == {}
    assert {game["status"] for game in data.get_nfl_schedule("2026")} == {
        "complete",
        "pre_game",
    }


def test_realistic_backend_exercises_six_player_comparison_cap(
    realistic_authenticated_app,
) -> None:
    app = realistic_authenticated_app()
    player_ids = ["qb-1", "rb-1", "wr-1", "te-1", "k-1", "def-1"]
    app.session_state["comparison-player-ids-league-1"] = player_ids
    app.session_state["generated-comparison-player-ids-league-1"] = player_ids

    app.switch_page("pages/comparison.py").run()

    assert app.session_state["generated-comparison-player-ids-league-1"] == (
        player_ids[:5]
    )


def test_realistic_backend_distinguishes_flex_and_mixed_position_groups(
    realistic_authenticated_app,
) -> None:
    flex_app = realistic_authenticated_app()
    flex_ids = ["rb-1", "wr-1", "te-1"]
    flex_app.session_state["comparison-player-ids-league-1"] = flex_ids
    flex_app.session_state["generated-comparison-player-ids-league-1"] = flex_ids
    flex_app.switch_page("pages/comparison.py").run()

    flex_stats = flex_app.selectbox(key="comparison-performance-league-1-stat").options
    assert "Rush Yds" in flex_stats
    assert "Receptions" in flex_stats
    assert "Opportunity" in [tab.label for tab in flex_app.tabs]

    mixed_app = realistic_authenticated_app()
    mixed_ids = ["qb-1", "k-1", "def-1"]
    mixed_app.session_state["comparison-player-ids-league-1"] = mixed_ids
    mixed_app.session_state["generated-comparison-player-ids-league-1"] = mixed_ids
    mixed_app.switch_page("pages/comparison.py").run()

    assert mixed_app.selectbox(key="comparison-performance-league-1-stat").options == [
        "Fantasy Points"
    ]
    assert any(
        "different position groups" in warning.value for warning in mixed_app.warning
    )

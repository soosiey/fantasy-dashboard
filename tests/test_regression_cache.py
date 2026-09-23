from pathlib import Path

from fantasy_dashboard import regression_cache
from fantasy_dashboard.backtesting import SnapshotWeek
from fantasy_dashboard.regression_cache import (
    load_or_create_regression_artifact,
    updated_projected_points,
)


def _historical_stats(season: str, week: int) -> dict[str, dict]:
    return {
        f"player-{index}": {
            "gp": 1,
            "pts": 10 + index + week / 10 + (int(season) - 2024),
        }
        for index in range(3)
    }


def _historical_projections(season: str, week: int, **kwargs) -> dict[str, dict]:
    del kwargs
    return {
        f"player-{index}": {"gp": 1, "pts": 9 + index + week / 10} for index in range(3)
    }


def test_regression_artifact_persists_and_reloads_without_retraining(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(regression_cache, "REGRESSION_CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        regression_cache.data,
        "get_player_stats",
        lambda season, season_type, week: _historical_stats(season, week),
    )
    monkeypatch.setattr(
        regression_cache.data,
        "get_projected_player_stats",
        _historical_projections,
    )
    players = {f"player-{index}": {"position": "QB"} for index in range(3)}
    snapshot = SnapshotWeek(
        season=2026,
        week=1,
        projection_run_id="pre-1",
        actual_run_id="post-1",
        projected_at="2026-09-01T00:00:00Z",
        actual_captured_at="2026-09-09T00:00:00Z",
        projections=_historical_projections("2026", 1),
        actuals=_historical_stats("2026", 1),
    )

    created = load_or_create_regression_artifact(
        "league-1", 2026, players, {"pts": 1}, {1: snapshot}
    )

    assert created is not None
    assert not created.loaded_from_cache
    assert created.validation_predictions
    assert created.backtest_predictions
    assert (tmp_path / "league1_2026.json").is_file()

    monkeypatch.setattr(
        regression_cache.data,
        "get_player_stats",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("retrained")),
    )
    loaded = load_or_create_regression_artifact(
        "league-1", 2026, players, {"pts": 1}, {1: snapshot}
    )

    assert loaded is not None
    assert loaded.loaded_from_cache
    assert loaded.validation_predictions == created.validation_predictions
    assert loaded.backtest_predictions == created.backtest_predictions

    updated = updated_projected_points(
        loaded,
        _historical_projections("2026", 2),
        players,
        {"pts": 1},
        2,
    )
    assert set(updated) == set(players)
    assert all(value >= 0 for value in updated.values())

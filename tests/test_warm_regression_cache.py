from pathlib import Path

import warm_regression_cache


def test_cli_warms_every_requested_league(monkeypatch, tmp_path: Path) -> None:
    warmed = []
    monkeypatch.setattr(
        warm_regression_cache,
        "warm_league_cache",
        lambda storage_dir, league_id: warmed.append((storage_dir, league_id)),
    )

    result = warm_regression_cache.main(
        [
            "--storage-dir",
            str(tmp_path),
            "--league-id",
            "league-1",
            "--league-id",
            "league-2",
        ]
    )

    assert result == 0
    assert warmed == [(tmp_path, "league-1"), (tmp_path, "league-2")]


def test_cli_attempts_remaining_leagues_after_one_failure(monkeypatch) -> None:
    warmed = []

    def warm(storage_dir: Path, league_id: str) -> None:
        del storage_dir
        warmed.append(league_id)
        if league_id == "league-1":
            raise ValueError("failed")

    monkeypatch.setattr(warm_regression_cache, "warm_league_cache", warm)

    result = warm_regression_cache.main(
        ["--league-id", "league-1", "--league-id", "league-2"]
    )

    assert result == 1
    assert warmed == ["league-1", "league-2"]

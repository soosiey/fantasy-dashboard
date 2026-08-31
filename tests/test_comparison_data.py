from types import SimpleNamespace

from fantasy_dashboard.components import comparison_data


def test_comparison_data_provider_reuses_full_season_data(
    monkeypatch,
) -> None:
    calls = {"actual": 0, "projected": 0, "rosters": 0, "schedule": 0}

    def get_actual_stats(
        season: str,
        season_type: str,
        week: int,
    ) -> dict[str, dict[str, float]]:
        assert season == "2026"
        assert season_type == "regular"
        calls["actual"] += 1
        return {"p1": {"gp": 1, "pts_ppr": float(week)}}

    def get_projected_stats(
        season: str,
        week: int,
    ) -> dict[str, dict[str, float]]:
        assert season == "2026"
        calls["projected"] += 1
        return {"p1": {"pts_ppr": float(week + 1)}}

    def get_roster_data(league_id: str) -> SimpleNamespace:
        assert league_id == "league-1"
        calls["rosters"] += 1
        return SimpleNamespace(
            rosters=[SimpleNamespace(players=["p1", "p2"])]
        )

    def get_schedule_data(
        season: str,
        season_type: str,
    ) -> list[dict[str, str]]:
        assert season == "2026"
        assert season_type == "regular"
        calls["schedule"] += 1
        return [{"season": season}]

    monkeypatch.setattr(
        comparison_data.data,
        "get_player_stats",
        get_actual_stats,
    )
    monkeypatch.setattr(
        comparison_data.data,
        "get_projected_player_stats",
        get_projected_stats,
    )
    monkeypatch.setattr(comparison_data.data, "get_rosters", get_roster_data)
    monkeypatch.setattr(
        comparison_data.data,
        "get_nfl_schedule",
        get_schedule_data,
    )

    provider = comparison_data.ComparisonDataProvider(
        "league-1",
        SimpleNamespace(scoring_settings={"pts_ppr": 1}),
        {
            "p1": {"position": "WR", "first_name": "One"},
            "p2": {"position": "WR", "first_name": "Two"},
        },
        ["p1"],
    )

    full_context = provider.get_context(
        "2026", comparison_data.FULL_SEASON_WEEKS
    )
    repeated_context = provider.get_context(
        "2026", comparison_data.FULL_SEASON_WEEKS
    )
    subset_context = provider.get_context("2026", [1, 2, 3])

    assert repeated_context is full_context
    assert [row["Week"] for row in subset_context.actual_rows["p1"]] == [
        1,
        2,
        3,
    ]
    assert calls == {
        "actual": 18,
        "projected": 18,
        "rosters": 1,
        "schedule": 1,
    }

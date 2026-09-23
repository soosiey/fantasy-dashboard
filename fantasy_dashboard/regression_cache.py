import hashlib
import json
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests

from fantasy_dashboard import backtesting, data
from fantasy_dashboard.backtesting import SnapshotWeek
from fantasy_dashboard.paths import REGRESSION_CACHE_DIR
from fantasy_dashboard.player_regression import (
    RegressionPrediction,
    RidgeResidualModel,
    build_regression_features,
    build_regression_observations,
    fit_final_residual_models,
    run_sequential_season_predictions,
    select_adjustment_weight,
)
from fantasy_dashboard.player_stats import calculate_fantasy_points

CACHE_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class RegressionArtifact:
    context_key: str
    season: int
    completed_weeks: tuple[int, ...]
    validation_predictions: tuple[RegressionPrediction, ...]
    backtest_predictions: tuple[RegressionPrediction, ...]
    best_adjustment_weight: float
    final_models: dict[str, RidgeResidualModel]
    actual_history: dict[str, tuple[float, ...]]
    residual_history: dict[str, tuple[float, ...]]
    unavailable_historical_inputs: int
    loaded_from_cache: bool = False


def _context_key(
    league_id: str,
    season: int,
    players: dict[str, dict[str, Any]],
    scoring_settings: dict[str, Any],
    snapshot_weeks: dict[int, SnapshotWeek],
) -> str:
    context = {
        "schema": CACHE_SCHEMA_VERSION,
        "league_id": str(league_id),
        "season": season,
        "scoring_settings": scoring_settings,
        "positions": {
            player_id: player.get("position") for player_id, player in players.items()
        },
        "snapshot_runs": {
            str(week): [snapshot.projection_run_id, snapshot.actual_run_id]
            for week, snapshot in snapshot_weeks.items()
        },
    }
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _cache_path(
    league_id: str,
    season: int,
    cache_dir: Path | None = None,
) -> Path:
    safe_league_id = "".join(
        character for character in str(league_id) if character.isalnum()
    )
    return Path(cache_dir or REGRESSION_CACHE_DIR) / f"{safe_league_id}_{season}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(payload, temporary_file, sort_keys=True, separators=(",", ":"))
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _serialize(artifact: RegressionArtifact) -> dict[str, Any]:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "context_key": artifact.context_key,
        "season": artifact.season,
        "completed_weeks": list(artifact.completed_weeks),
        "validation_predictions": [
            asdict(prediction) for prediction in artifact.validation_predictions
        ],
        "backtest_predictions": [
            asdict(prediction) for prediction in artifact.backtest_predictions
        ],
        "best_adjustment_weight": artifact.best_adjustment_weight,
        "final_models": {
            position: asdict(model) for position, model in artifact.final_models.items()
        },
        "actual_history": {
            player_id: list(values)
            for player_id, values in artifact.actual_history.items()
        },
        "residual_history": {
            player_id: list(values)
            for player_id, values in artifact.residual_history.items()
        },
        "unavailable_historical_inputs": artifact.unavailable_historical_inputs,
    }


def _deserialize(
    payload: dict[str, Any], context_key: str
) -> RegressionArtifact | None:
    if (
        payload.get("schema_version") != CACHE_SCHEMA_VERSION
        or payload.get("context_key") != context_key
    ):
        return None
    try:
        return RegressionArtifact(
            context_key=context_key,
            season=int(payload["season"]),
            completed_weeks=tuple(int(week) for week in payload["completed_weeks"]),
            validation_predictions=tuple(
                RegressionPrediction(**prediction)
                for prediction in payload["validation_predictions"]
            ),
            backtest_predictions=tuple(
                RegressionPrediction(**prediction)
                for prediction in payload["backtest_predictions"]
            ),
            best_adjustment_weight=float(payload["best_adjustment_weight"]),
            final_models={
                position: RidgeResidualModel(**model)
                for position, model in payload["final_models"].items()
            },
            actual_history={
                player_id: tuple(float(value) for value in values)
                for player_id, values in payload["actual_history"].items()
            },
            residual_history={
                player_id: tuple(float(value) for value in values)
                for player_id, values in payload["residual_history"].items()
            },
            unavailable_historical_inputs=int(
                payload.get("unavailable_historical_inputs", 0)
            ),
            loaded_from_cache=True,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _current_histories(
    snapshot_weeks: dict[int, SnapshotWeek],
    scoring_settings: dict[str, Any],
) -> tuple[dict[str, tuple[float, ...]], dict[str, tuple[float, ...]]]:
    actual_history: dict[str, list[float]] = {}
    residual_history: dict[str, list[float]] = {}
    for week in sorted(snapshot_weeks):
        snapshot = snapshot_weeks[week]
        for player_id, actual_stats in snapshot.actuals.items():
            games = actual_stats.get("gp")
            played = (
                float(games) > 0
                if isinstance(games, Real)
                else any(
                    isinstance(value, Real) and float(value) != 0
                    for value in actual_stats.values()
                )
            )
            if not played:
                continue
            actual_points = calculate_fantasy_points(actual_stats, scoring_settings)
            actual_history.setdefault(player_id, []).append(actual_points)
            projection_stats = snapshot.projections.get(player_id)
            if projection_stats is not None:
                projected_points = calculate_fantasy_points(
                    projection_stats, scoring_settings
                )
                residual_history.setdefault(player_id, []).append(
                    actual_points - projected_points
                )
    return (
        {player_id: tuple(values) for player_id, values in actual_history.items()},
        {player_id: tuple(values) for player_id, values in residual_history.items()},
    )


def load_or_create_regression_artifact(
    league_id: str,
    season: int,
    players: dict[str, dict[str, Any]],
    scoring_settings: dict[str, Any],
    snapshot_weeks: dict[int, SnapshotWeek] | None = None,
    cache_dir: Path | None = None,
) -> RegressionArtifact | None:
    snapshots = snapshot_weeks or backtesting.load_completed_snapshot_weeks(
        league_id, season
    )
    if not snapshots:
        return None
    context_key = _context_key(league_id, season, players, scoring_settings, snapshots)
    path = _cache_path(league_id, season, cache_dir)
    if path.is_file():
        try:
            cached = _deserialize(
                json.loads(path.read_text(encoding="utf-8")), context_key
            )
        except (OSError, json.JSONDecodeError):
            cached = None
        if cached is not None:
            return cached

    historical_seasons = (season - 2, season - 1)
    actuals_by_season_week: dict[int, dict] = {}
    projections_by_season_week: dict[int, dict] = {}
    unavailable = 0
    for historical_season in historical_seasons:
        actuals_by_season_week[historical_season] = {}
        projections_by_season_week[historical_season] = {}
        for week in range(1, 19):
            try:
                actuals_by_season_week[historical_season][week] = data.get_player_stats(
                    str(historical_season), "regular", week
                )
                projections_by_season_week[historical_season][week] = (
                    data.get_projected_player_stats(
                        str(historical_season), week, baseline_only=True
                    )
                )
            except (OSError, requests.RequestException, TypeError, ValueError):
                unavailable += 1
    actuals_by_season_week[season] = {
        week: snapshot.actuals for week, snapshot in snapshots.items()
    }
    projections_by_season_week[season] = {
        week: snapshot.projections for week, snapshot in snapshots.items()
    }
    player_positions = {
        player_id: {"position": player.get("position")}
        for player_id, player in players.items()
    }
    observations = build_regression_observations(
        actuals_by_season_week,
        projections_by_season_week,
        player_positions,
        scoring_settings,
    )
    alpha_season = season - 2
    validation_predictions = run_sequential_season_predictions(
        observations,
        season - 1,
        alpha_training_season=alpha_season,
    )
    actual_history, residual_history = _current_histories(snapshots, scoring_settings)
    artifact = RegressionArtifact(
        context_key=context_key,
        season=season,
        completed_weeks=tuple(sorted(snapshots)),
        validation_predictions=validation_predictions,
        backtest_predictions=run_sequential_season_predictions(
            observations,
            season,
            alpha_training_season=alpha_season,
        ),
        best_adjustment_weight=select_adjustment_weight(validation_predictions),
        final_models=fit_final_residual_models(
            observations,
            alpha_training_season=alpha_season,
        ),
        actual_history=actual_history,
        residual_history=residual_history,
        unavailable_historical_inputs=unavailable,
    )
    _write_json(path, _serialize(artifact))
    return artifact


def updated_projected_points(
    artifact: RegressionArtifact,
    projected_stats: dict[str, dict[str, Any]],
    players: dict[str, dict[str, Any]],
    scoring_settings: dict[str, Any],
    week: int | None,
) -> dict[str, float]:
    if week is not None and week in artifact.completed_weeks:
        return {
            prediction.player_id: prediction.adjusted_projection
            for prediction in artifact.backtest_predictions
            if prediction.week == week
        }

    forecast_week = week or min(max(artifact.completed_weeks, default=0) + 1, 18)
    updated: dict[str, float] = {}
    for player_id, stats in projected_stats.items():
        position = str(players.get(player_id, {}).get("position") or "")
        model = artifact.final_models.get(position)
        if model is None:
            continue
        projection = calculate_fantasy_points(stats, scoring_settings)
        games = float(stats.get("gp") or 1.0) if week is None else 1.0
        per_game_projection = projection / games if games > 0 else projection
        features = build_regression_features(
            per_game_projection,
            list(artifact.actual_history.get(player_id, ())),
            list(artifact.residual_history.get(player_id, ())),
            forecast_week,
        )
        adjustment = model.predict(features)
        updated[player_id] = max(0.0, projection + games * adjustment)
    return updated


def get_updated_projected_points(
    league_id: str,
    season: int,
    projected_stats: dict[str, dict[str, Any]],
    players: dict[str, dict[str, Any]],
    scoring_settings: dict[str, Any],
    week: int | None,
) -> dict[str, float]:
    artifact = load_or_create_regression_artifact(
        league_id,
        season,
        players,
        scoring_settings,
    )
    if artifact is None:
        return {}
    return updated_projected_points(
        artifact,
        projected_stats,
        players,
        scoring_settings,
        week,
    )

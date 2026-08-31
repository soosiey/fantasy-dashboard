from collections import defaultdict
from dataclasses import dataclass
from math import sqrt
from numbers import Real
from statistics import fmean, pstdev
from typing import Any

import numpy as np

from fantasy_dashboard.player_stats import calculate_fantasy_points

FEATURE_NAMES = (
    "Provider projection",
    "Previous actual",
    "3-game actual average",
    "5-game actual average",
    "3-game residual average",
    "5-game residual average",
    "5-game scoring volatility",
    "Prior games observed",
    "Season progress",
)
SUPPORTED_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 100.0, 1000.0)


@dataclass(frozen=True, slots=True)
class RegressionObservation:
    season: int
    week: int
    player_id: str
    position: str
    provider_projection: float
    actual_points: float
    provider_residual: float
    features: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RidgeResidualModel:
    alpha: float
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    observations: int

    def predict(self, features: tuple[float, ...]) -> float:
        standardized = (
            (np.asarray(features, dtype=float) - np.asarray(self.feature_means))
            / np.asarray(self.feature_scales)
        )
        return float(self.intercept + standardized @ np.asarray(self.coefficients))


@dataclass(frozen=True, slots=True)
class RegressionPrediction:
    season: int
    week: int
    player_id: str
    position: str
    actual_points: float
    provider_projection: float
    predicted_adjustment: float
    adjusted_projection: float

    @property
    def provider_residual(self) -> float:
        return self.actual_points - self.provider_projection

    @property
    def model_residual(self) -> float:
        return self.actual_points - self.adjusted_projection


@dataclass(frozen=True, slots=True)
class RegressionEvaluation:
    position: str
    observations: int
    alpha: float
    provider_mae: float
    model_mae: float
    provider_rmse: float
    model_rmse: float
    provider_bias: float
    model_bias: float
    model_r_squared: float

    @property
    def mae_improvement(self) -> float:
        if self.provider_mae <= 0:
            return 0.0
        return (self.provider_mae - self.model_mae) / self.provider_mae


@dataclass(frozen=True, slots=True)
class PlayerRegressionSummary:
    player_id: str
    position: str
    observations: int
    actual_average: float
    provider_average: float
    provider_residual_average: float
    adjustment_average: float
    adjusted_average: float
    model_residual_average: float
    provider_mae: float
    model_mae: float

    @property
    def mae_improvement(self) -> float:
        if self.provider_mae <= 0:
            return 0.0
        return (self.provider_mae - self.model_mae) / self.provider_mae


@dataclass(frozen=True, slots=True)
class RegressionReport:
    observations: tuple[RegressionObservation, ...]
    predictions: tuple[RegressionPrediction, ...]
    evaluations: tuple[RegressionEvaluation, ...]
    player_summaries: tuple[PlayerRegressionSummary, ...]
    final_models: dict[str, RidgeResidualModel]


def _average(values: list[float], count: int) -> float:
    return fmean(values[-count:]) if values else 0.0


def _played(stats: dict[str, Any]) -> bool:
    games = stats.get("gp")
    if isinstance(games, Real):
        return float(games) > 0
    return any(isinstance(value, Real) and float(value) != 0 for value in stats.values())


def build_regression_observations(
    actuals_by_season_week: dict[int, dict[int, dict[str, dict[str, Any]]]],
    projections_by_season_week: dict[int, dict[int, dict[str, dict[str, Any]]]],
    players: dict[str, dict[str, Any]],
    scoring_settings: dict[str, Any],
) -> list[RegressionObservation]:
    observations: list[RegressionObservation] = []
    for season in sorted(set(actuals_by_season_week) & set(projections_by_season_week)):
        actual_history: dict[str, list[float]] = defaultdict(list)
        residual_history: dict[str, list[float]] = defaultdict(list)
        actual_weeks = actuals_by_season_week[season]
        projection_weeks = projections_by_season_week[season]
        for week in sorted(set(actual_weeks) & set(projection_weeks)):
            actuals = actual_weeks[week]
            projections = projection_weeks[week]
            for player_id in sorted(set(actuals) & set(projections)):
                actual_stats = actuals[player_id]
                if not _played(actual_stats):
                    continue
                position = str(players.get(player_id, {}).get("position") or "")
                if position not in SUPPORTED_POSITIONS:
                    continue
                provider_projection = calculate_fantasy_points(
                    projections[player_id], scoring_settings
                )
                if provider_projection <= 0:
                    continue
                actual_points = calculate_fantasy_points(actual_stats, scoring_settings)
                prior_actuals = actual_history[player_id]
                prior_residuals = residual_history[player_id]
                features = (
                    provider_projection,
                    prior_actuals[-1] if prior_actuals else 0.0,
                    _average(prior_actuals, 3),
                    _average(prior_actuals, 5),
                    _average(prior_residuals, 3),
                    _average(prior_residuals, 5),
                    pstdev(prior_actuals[-5:]) if len(prior_actuals) >= 2 else 0.0,
                    float(min(len(prior_actuals), 17)),
                    week / 18,
                )
                observations.append(
                    RegressionObservation(
                        season=season,
                        week=week,
                        player_id=player_id,
                        position=position,
                        provider_projection=provider_projection,
                        actual_points=actual_points,
                        provider_residual=actual_points - provider_projection,
                        features=features,
                    )
                )

            # Update histories only after every Week t feature has been constructed.
            for player_id, actual_stats in actuals.items():
                if not _played(actual_stats):
                    continue
                actual_points = calculate_fantasy_points(actual_stats, scoring_settings)
                actual_history[player_id].append(actual_points)
                projected_stats = projections.get(player_id)
                if projected_stats is not None:
                    projection = calculate_fantasy_points(
                        projected_stats, scoring_settings
                    )
                    residual_history[player_id].append(actual_points - projection)
    return observations


def fit_ridge_residual_model(
    observations: list[RegressionObservation], alpha: float
) -> RidgeResidualModel | None:
    if len(observations) < len(FEATURE_NAMES) + 2:
        return None
    features = np.asarray([observation.features for observation in observations])
    targets = np.asarray(
        [observation.provider_residual for observation in observations]
    )
    means = features.mean(axis=0)
    scales = features.std(axis=0)
    scales[scales < 1e-9] = 1.0
    standardized = (features - means) / scales
    centered_targets = targets - targets.mean()
    system = standardized.T @ standardized + float(alpha) * np.eye(
        standardized.shape[1]
    )
    try:
        coefficients = np.linalg.solve(system, standardized.T @ centered_targets)
    except np.linalg.LinAlgError:
        coefficients = np.linalg.pinv(system) @ standardized.T @ centered_targets
    return RidgeResidualModel(
        alpha=float(alpha),
        feature_means=tuple(float(value) for value in means),
        feature_scales=tuple(float(value) for value in scales),
        coefficients=tuple(float(value) for value in coefficients),
        intercept=float(targets.mean()),
        observations=len(observations),
    )


def select_ridge_alpha(
    observations: list[RegressionObservation], training_season: int
) -> float:
    season_rows = [
        observation
        for observation in observations
        if observation.season == training_season
    ]
    weeks = sorted({observation.week for observation in season_rows})
    errors = {alpha: [] for alpha in RIDGE_ALPHAS}
    for week in weeks:
        training = [row for row in season_rows if row.week < week]
        validation = [row for row in season_rows if row.week == week]
        if len(training) < 40 or not validation:
            continue
        for alpha in RIDGE_ALPHAS:
            model = fit_ridge_residual_model(training, alpha)
            if model is None:
                continue
            errors[alpha].extend(
                abs(row.provider_residual - model.predict(row.features))
                for row in validation
            )
    return min(
        RIDGE_ALPHAS,
        key=lambda alpha: fmean(errors[alpha]) if errors[alpha] else float("inf"),
    )


def _evaluation(
    position: str,
    predictions: list[RegressionPrediction],
    alpha: float,
) -> RegressionEvaluation:
    provider_errors = [prediction.provider_residual for prediction in predictions]
    model_errors = [prediction.model_residual for prediction in predictions]
    actuals = [prediction.actual_points for prediction in predictions]
    actual_mean = fmean(actuals)
    total_variation = sum((actual - actual_mean) ** 2 for actual in actuals)
    squared_model_error = sum(error**2 for error in model_errors)
    return RegressionEvaluation(
        position=position,
        observations=len(predictions),
        alpha=alpha,
        provider_mae=fmean(abs(error) for error in provider_errors),
        model_mae=fmean(abs(error) for error in model_errors),
        provider_rmse=sqrt(fmean(error**2 for error in provider_errors)),
        model_rmse=sqrt(fmean(error**2 for error in model_errors)),
        provider_bias=fmean(provider_errors),
        model_bias=fmean(model_errors),
        model_r_squared=(
            1 - squared_model_error / total_variation
            if total_variation > 0
            else 0.0
        ),
    )


def _player_summary(
    player_id: str, predictions: list[RegressionPrediction]
) -> PlayerRegressionSummary:
    provider_errors = [prediction.provider_residual for prediction in predictions]
    model_errors = [prediction.model_residual for prediction in predictions]
    return PlayerRegressionSummary(
        player_id=player_id,
        position=predictions[0].position,
        observations=len(predictions),
        actual_average=fmean(prediction.actual_points for prediction in predictions),
        provider_average=fmean(
            prediction.provider_projection for prediction in predictions
        ),
        provider_residual_average=fmean(provider_errors),
        adjustment_average=fmean(
            prediction.predicted_adjustment for prediction in predictions
        ),
        adjusted_average=fmean(
            prediction.adjusted_projection for prediction in predictions
        ),
        model_residual_average=fmean(model_errors),
        provider_mae=fmean(abs(error) for error in provider_errors),
        model_mae=fmean(abs(error) for error in model_errors),
    )


def run_ridge_regression_evaluation(
    observations: list[RegressionObservation],
    *,
    training_season: int = 2024,
    evaluation_season: int = 2025,
) -> RegressionReport:
    alphas = {
        position: select_ridge_alpha(
            [row for row in observations if row.position == position], training_season
        )
        for position in SUPPORTED_POSITIONS
    }
    predictions: list[RegressionPrediction] = []
    for week in sorted(
        {
            row.week
            for row in observations
            if row.season == evaluation_season
        }
    ):
        for position in SUPPORTED_POSITIONS:
            training = [
                row
                for row in observations
                if row.position == position
                and (
                    row.season == training_season
                    or (row.season == evaluation_season and row.week < week)
                )
            ]
            evaluation = [
                row
                for row in observations
                if row.position == position
                and row.season == evaluation_season
                and row.week == week
            ]
            model = fit_ridge_residual_model(training, alphas[position])
            if model is None:
                continue
            for row in evaluation:
                adjustment = model.predict(row.features)
                adjusted_projection = max(0.0, row.provider_projection + adjustment)
                predictions.append(
                    RegressionPrediction(
                        season=row.season,
                        week=row.week,
                        player_id=row.player_id,
                        position=row.position,
                        actual_points=row.actual_points,
                        provider_projection=row.provider_projection,
                        predicted_adjustment=adjustment,
                        adjusted_projection=adjusted_projection,
                    )
                )

    predictions_by_position: dict[str, list[RegressionPrediction]] = defaultdict(list)
    predictions_by_player: dict[str, list[RegressionPrediction]] = defaultdict(list)
    for prediction in predictions:
        predictions_by_position[prediction.position].append(prediction)
        predictions_by_player[prediction.player_id].append(prediction)
    evaluations = [
        _evaluation(position, rows, alphas[position])
        for position, rows in predictions_by_position.items()
        if rows
    ]
    if predictions:
        evaluations.insert(0, _evaluation("Overall", predictions, 0.0))

    final_models = {}
    for position in SUPPORTED_POSITIONS:
        rows = [row for row in observations if row.position == position]
        model = fit_ridge_residual_model(rows, alphas[position])
        if model is not None:
            final_models[position] = model

    return RegressionReport(
        observations=tuple(observations),
        predictions=tuple(predictions),
        evaluations=tuple(evaluations),
        player_summaries=tuple(
            sorted(
                (
                    _player_summary(player_id, rows)
                    for player_id, rows in predictions_by_player.items()
                ),
                key=lambda summary: (-summary.observations, summary.player_id),
            )
        ),
        final_models=final_models,
    )

from dataclasses import dataclass
from math import erf, exp, sqrt
from numbers import Real
from typing import Any


@dataclass(frozen=True, slots=True)
class LiveGameContext:
    home: str
    away: str
    home_score: int
    away_score: int
    elapsed_fraction: float
    possession: str = ""
    completed: bool = False


def _number(value: Any) -> float:
    return float(value) if isinstance(value, Real) else 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def parse_espn_live_games(payload: dict[str, Any]) -> list[LiveGameContext]:
    """Extract the small amount of live scoreboard state used by the model."""
    games: list[LiveGameContext] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        status = event.get("status") or {}
        status_type = status.get("type") or {}
        if status_type.get("state") not in {"in", "post"}:
            continue
        competitions = event.get("competitions") or []
        competition = competitions[0] if competitions else {}
        teams: dict[str, tuple[str, int]] = {}
        for competitor in competition.get("competitors") or []:
            team = competitor.get("team") or {}
            abbreviation = str(team.get("abbreviation") or "").upper()
            try:
                score = int(float(competitor.get("score") or 0))
            except (TypeError, ValueError):
                score = 0
            teams[str(competitor.get("homeAway") or "")] = (abbreviation, score)
        if "home" not in teams or "away" not in teams:
            continue

        period = max(int(status.get("period") or 1), 1)
        clock = _clamp(_number(status.get("clock")), 0.0, 900.0)
        elapsed_seconds = min((period - 1) * 900 + (900 - clock), 3600)
        if "HALFTIME" in str(status_type.get("name") or "").upper():
            elapsed_seconds = 1800
        situation = competition.get("situation") or {}
        raw_possession = situation.get("possession")
        possession_id = str(
            raw_possession.get("id")
            if isinstance(raw_possession, dict)
            else raw_possession or ""
        )
        possession = next(
            (
                str((competitor.get("team") or {}).get("abbreviation") or "").upper()
                for competitor in competition.get("competitors") or []
                if str((competitor.get("team") or {}).get("id") or "")
                == possession_id
            ),
            "",
        )
        games.append(
            LiveGameContext(
                home=teams["home"][0],
                away=teams["away"][0],
                home_score=teams["home"][1],
                away_score=teams["away"][1],
                elapsed_fraction=(
                    1.0 if status_type.get("state") == "post"
                    else _clamp(elapsed_seconds / 3600, 0.0, 1.0)
                ),
                completed=status_type.get("state") == "post",
                possession=possession,
            )
        )
    return games


def _team_total(
    player_ids: list[str], stats: dict[str, dict[str, Any]], field: str
) -> float:
    return sum(_number(stats.get(player_id, {}).get(field)) for player_id in player_ids)


def _blended_rate(
    prior_numerator: float,
    prior_denominator: float,
    observed_numerator: float,
    observed_denominator: float,
    prior_strength: float,
) -> float:
    prior = prior_numerator / prior_denominator if prior_denominator else 0.0
    if observed_denominator <= 0:
        return prior
    weight = observed_denominator / (observed_denominator + prior_strength)
    observed = observed_numerator / observed_denominator
    return (1 - weight) * prior + weight * observed


def _remaining_share(
    player_id: str,
    player_ids: list[str],
    baseline: dict[str, dict[str, Any]],
    actual: dict[str, dict[str, Any]],
    field: str,
    prior_strength: float = 12.0,
) -> float:
    prior_total = _team_total(player_ids, baseline, field)
    actual_total = _team_total(player_ids, actual, field)
    return _blended_rate(
        _number(baseline.get(player_id, {}).get(field)),
        prior_total,
        _number(actual.get(player_id, {}).get(field)),
        actual_total,
        prior_strength,
    )


def _efficiency(
    baseline: dict[str, Any],
    actual: dict[str, Any],
    numerator: str,
    denominator: str,
) -> float:
    """Let efficiency move slowly while opportunity shares react more quickly."""
    prior_denominator = _number(baseline.get(denominator))
    prior = _number(baseline.get(numerator)) / prior_denominator if prior_denominator else 0
    observed_denominator = _number(actual.get(denominator))
    if observed_denominator <= 0:
        return prior
    observed = _number(actual.get(numerator)) / observed_denominator
    observed_weight = 0.35 * observed_denominator / (observed_denominator + 40)
    return (1 - observed_weight) * prior + observed_weight * observed


def _is_unavailable(player: dict[str, Any]) -> bool:
    status = str(player.get("status") or "").strip().casefold()
    injury = str(player.get("injury_status") or "").strip().casefold()
    return player.get("active") is False or status in {
        "inactive",
        "ineligible",
    } or injury in {"out", "ir", "pup", "suspended"}


POINTS_ALLOWED_BUCKETS = {
    "pts_allow_0": (0, 0),
    "pts_allow_1_6": (1, 6),
    "pts_allow_7_13": (7, 13),
    "pts_allow_14_20": (14, 20),
    "pts_allow_21_27": (21, 27),
    "pts_allow_28_34": (28, 34),
    "pts_allow_35p": (35, None),
}
YARDS_ALLOWED_BUCKETS = {
    "yds_allow_0_100": (0, 100),
    "yds_allow_100_199": (101, 199),
    "yds_allow_200_299": (200, 299),
    "yds_allow_300_349": (300, 349),
    "yds_allow_350_399": (350, 399),
    "yds_allow_400_449": (400, 449),
    "yds_allow_450_499": (450, 499),
    "yds_allow_500_549": (500, 549),
    "yds_allow_550p": (550, None),
}


def _expected_remaining_total(
    baseline_total: float, observed_total: float, elapsed_fraction: float
) -> float:
    if elapsed_fraction <= 0:
        return max(baseline_total, 0)
    observed_full_game_rate = observed_total / elapsed_fraction
    observed_weight = elapsed_fraction / (elapsed_fraction + 0.5)
    blended_full_game_rate = (
        (1 - observed_weight) * baseline_total
        + observed_weight * observed_full_game_rate
    )
    return max(blended_full_game_rate * (1 - elapsed_fraction), 0)


def _poisson_bucket_probabilities(
    current: int,
    expected_remaining: float,
    buckets: dict[str, tuple[int, int | None]],
) -> dict[str, float]:
    probabilities = {key: 0.0 for key in buckets}
    probability = exp(-expected_remaining)
    covered = 0.0
    # Seventy remaining points is already deep in the tail for an NFL team.
    for remaining in range(71):
        final_total = current + remaining
        key = next(
            key
            for key, (low, high) in buckets.items()
            if final_total >= low and (high is None or final_total <= high)
        )
        probabilities[key] += probability
        covered += probability
        probability *= expected_remaining / (remaining + 1)
    probabilities[next(reversed(buckets))] += max(0.0, 1 - covered)
    return probabilities


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + erf(value / sqrt(2)))


def _yardage_bucket_probabilities(
    current: float,
    expected_remaining: float,
) -> dict[str, float]:
    deviation = max(35.0, 4 * sqrt(expected_remaining))
    below_zero = _normal_cdf(-expected_remaining / deviation)
    normalizer = max(1 - below_zero, 1e-12)

    def remaining_cdf(value: float) -> float:
        if value < 0:
            return 0.0
        raw = _normal_cdf((value - expected_remaining) / deviation)
        return _clamp((raw - below_zero) / normalizer, 0.0, 1.0)

    probabilities: dict[str, float] = {}
    for key, (low, high) in YARDS_ALLOWED_BUCKETS.items():
        lower_probability = remaining_cdf(low - current - 1)
        upper_probability = 1.0 if high is None else remaining_cdf(high - current)
        probabilities[key] = max(0.0, upper_probability - lower_probability)
    total = sum(probabilities.values())
    if total:
        probabilities = {key: value / total for key, value in probabilities.items()}
    return probabilities


def _build_defense_projection(
    baseline: dict[str, Any],
    actual: dict[str, Any],
    game: LiveGameContext,
    team: str,
) -> dict[str, float]:
    remaining_fraction = 1 - game.elapsed_fraction
    final = {
        key: _number(actual.get(key)) + _number(value) * remaining_fraction
        for key, value in baseline.items()
        if isinstance(value, Real)
        and key not in POINTS_ALLOWED_BUCKETS
        and key not in YARDS_ALLOWED_BUCKETS
    }
    for key, value in actual.items():
        if (
            isinstance(value, Real)
            and key not in final
            and key not in POINTS_ALLOWED_BUCKETS
            and key not in YARDS_ALLOWED_BUCKETS
        ):
            final[key] = _number(value)

    opponent_score = game.away_score if team == game.home else game.home_score
    remaining_points = _expected_remaining_total(
        _number(baseline.get("pts_allow")),
        float(opponent_score),
        game.elapsed_fraction,
    )
    final["pts_allow"] = opponent_score + remaining_points
    final.update(
        _poisson_bucket_probabilities(
            opponent_score,
            remaining_points,
            POINTS_ALLOWED_BUCKETS,
        )
    )

    current_yards = _number(actual.get("yds_allow"))
    remaining_yards = _expected_remaining_total(
        _number(baseline.get("yds_allow")),
        current_yards,
        game.elapsed_fraction,
    )
    final["yds_allow"] = current_yards + remaining_yards
    final.update(_yardage_bucket_probabilities(current_yards, remaining_yards))
    if "gp" in baseline or "gp" in actual:
        final["gp"] = 1.0
    return final


def build_live_projections(
    baseline: dict[str, dict[str, float]],
    actual: dict[str, dict[str, Any]],
    players: dict[str, dict[str, Any]],
    games: list[LiveGameContext],
) -> dict[str, dict[str, float]]:
    """Return live estimates and actual stat lines for completed NFL games."""
    projected = {player_id: dict(stats) for player_id, stats in baseline.items()}
    player_ids_by_team: dict[str, list[str]] = {}
    for player_id in set(baseline) | set(actual):
        team = str(players.get(player_id, {}).get("team") or "").upper()
        if team:
            player_ids_by_team.setdefault(team, []).append(player_id)

    game_by_team = {team: game for game in games for team in (game.home, game.away)}
    for team, game in game_by_team.items():
        team_ids = player_ids_by_team.get(team, [])
        if not team_ids:
            continue
        if game.completed:
            for player_id in team_ids:
                projected[player_id] = {
                    key: _number(value)
                    for key, value in actual.get(player_id, {}).items()
                    if isinstance(value, Real)
                }
            continue
        remaining_fraction = 1 - game.elapsed_fraction
        baseline_passes = _team_total(team_ids, baseline, "pass_att")
        baseline_rushes = _team_total(team_ids, baseline, "rush_att")
        expected_plays = _clamp(baseline_passes + baseline_rushes, 50, 80)
        actual_passes = _team_total(team_ids, actual, "pass_att")
        actual_rushes = _team_total(team_ids, actual, "rush_att")
        actual_plays = actual_passes + actual_rushes
        expected_elapsed_plays = expected_plays * max(game.elapsed_fraction, 0.05)
        observed_pace = actual_plays / expected_elapsed_plays if expected_elapsed_plays else 1
        pace_weight = game.elapsed_fraction / (game.elapsed_fraction + 0.35)
        pace = (1 - pace_weight) + pace_weight * _clamp(observed_pace, 0.75, 1.25)
        remaining_plays = expected_plays * remaining_fraction * pace
        if game.possession == team and remaining_fraction > 0:
            remaining_plays += 0.5

        prior_pass_rate = baseline_passes / expected_plays if expected_plays else 0.58
        pass_rate = _blended_rate(
            baseline_passes,
            expected_plays,
            actual_passes,
            actual_plays,
            25,
        )
        own_score = game.home_score if team == game.home else game.away_score
        opponent_score = game.away_score if team == game.home else game.home_score
        score_adjustment = _clamp((opponent_score - own_score) * 0.008, -0.12, 0.12)
        pass_rate = _clamp(0.7 * pass_rate + 0.3 * prior_pass_rate + score_adjustment, 0.35, 0.8)
        remaining_passes = remaining_plays * pass_rate
        remaining_rushes = remaining_plays - remaining_passes

        for player_id in team_ids:
            base = baseline.get(player_id, {})
            observed = actual.get(player_id, {})
            if player_id not in baseline:
                continue
            if _is_unavailable(players.get(player_id, {})):
                projected[player_id] = {
                    key: _number(value)
                    for key, value in observed.items()
                    if isinstance(value, Real)
                }
                continue
            if str(players.get(player_id, {}).get("position") or "").upper() == "DEF":
                projected[player_id] = _build_defense_projection(
                    base,
                    observed,
                    game,
                    team,
                )
                continue

            final = {
                key: _number(observed.get(key)) + _number(value) * remaining_fraction
                for key, value in base.items()
                if isinstance(value, Real)
            }
            for key, value in observed.items():
                if isinstance(value, Real) and key not in final:
                    final[key] = _number(value)

            player_passes = remaining_passes * _remaining_share(
                player_id, team_ids, baseline, actual, "pass_att", 8
            )
            player_rushes = remaining_rushes * _remaining_share(
                player_id, team_ids, baseline, actual, "rush_att"
            )
            player_targets = remaining_passes * _remaining_share(
                player_id, team_ids, baseline, actual, "rec_tgt"
            )
            modeled = {
                "pass_att": player_passes,
                "pass_cmp": player_passes
                * _efficiency(base, observed, "pass_cmp", "pass_att"),
                "pass_yd": player_passes
                * _efficiency(base, observed, "pass_yd", "pass_att"),
                "pass_td": player_passes
                * _efficiency(base, {}, "pass_td", "pass_att"),
                "pass_int": player_passes
                * _efficiency(base, {}, "pass_int", "pass_att"),
                "rush_att": player_rushes,
                "rush_yd": player_rushes
                * _efficiency(base, observed, "rush_yd", "rush_att"),
                "rush_td": player_rushes
                * _efficiency(base, {}, "rush_td", "rush_att"),
                "rec_tgt": player_targets,
                "rec": player_targets * _efficiency(base, observed, "rec", "rec_tgt"),
                "rec_yd": player_targets
                * _efficiency(base, observed, "rec_yd", "rec_tgt"),
                "rec_td": player_targets
                * _efficiency(base, {}, "rec_td", "rec_tgt"),
            }
            for key, remaining_value in modeled.items():
                if key in base or key in observed:
                    final[key] = _number(observed.get(key)) + remaining_value
            projected[player_id] = final
    return projected

import json
from collections.abc import Callable
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fantasy_dashboard.draft_grading import (
    DraftGradeWeights,
    DraftPickAlternative,
    DraftPickGrade,
)
from fantasy_dashboard.league_predictions import DraftTeamProjection
from fantasy_dashboard.paths import DRAFT_ANALYSIS_CACHE_DIR

CACHE_SCHEMA_VERSION = 1


def _cache_folder(draft_id: str) -> Path:
    draft_key = sha256(str(draft_id).encode()).hexdigest()[:24]
    return DRAFT_ANALYSIS_CACHE_DIR / draft_key


def _weights_key(weights: DraftGradeWeights) -> str:
    serialized = json.dumps(asdict(weights), sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode()).hexdigest()[:16]


def _read_payload(path: Path, kind: str) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
    except (OSError, TypeError, ValueError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != CACHE_SCHEMA_VERSION
        or payload.get("kind") != kind
        or not isinstance(payload.get("results"), dict)
    ):
        return None
    return payload


def _write_payload(path: Path, kind: str, results: dict[str, Any]) -> None:
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
            json.dump(
                {
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "kind": kind,
                    "results": results,
                },
                temporary_file,
                separators=(",", ":"),
            )
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_or_create_draft_pick_grades(
    draft_id: str,
    weights: DraftGradeWeights,
    calculate: Callable[[], dict[int, DraftPickGrade]],
) -> dict[int, DraftPickGrade]:
    """Load immutable completed-draft grades or calculate and persist them once."""
    path = _cache_folder(draft_id) / f"pick_grades_{_weights_key(weights)}.json"
    payload = _read_payload(path, "pick_grades")
    if payload is not None:
        try:
            grades = {}
            for pick_number, raw_grade in payload["results"].items():
                grade = dict(raw_grade)
                raw_alternatives = grade.pop("alternatives", None)
                alternatives = (
                    None
                    if raw_alternatives is None
                    else tuple(
                        DraftPickAlternative(**alternative)
                        for alternative in raw_alternatives
                    )
                )
                grades[int(pick_number)] = DraftPickGrade(
                    **grade,
                    alternatives=alternatives,
                )
            return grades
        except (TypeError, ValueError):
            pass

    grades = calculate()
    _write_payload(
        path,
        "pick_grades",
        {str(pick_number): asdict(grade) for pick_number, grade in grades.items()},
    )
    return grades


def load_or_create_draft_team_projections(
    draft_id: str,
    calculate: Callable[[], dict[str, DraftTeamProjection]],
) -> dict[str, DraftTeamProjection]:
    """Load immutable draft simulation results or calculate and persist them once."""
    path = _cache_folder(draft_id) / "team_projections.json"
    payload = _read_payload(path, "team_projections")
    if payload is not None:
        try:
            return {
                user_id: DraftTeamProjection(**projection)
                for user_id, projection in payload["results"].items()
            }
        except (TypeError, ValueError):
            pass

    projections = calculate()
    _write_payload(
        path,
        "team_projections",
        {user_id: asdict(projection) for user_id, projection in projections.items()},
    )
    return projections

import json
import re
import time
from datetime import timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests

ESPN_POSITION_MAP = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "DEF",
}

ESPN_TEAM_MAP = {
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",
    14: "LAR",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WAS",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}

# Translate ESPN's numeric fantasy stat IDs into Sleeper scoring-setting keys.
ESPN_STAT_MAP = {
    "0": ("pass_att",),
    "1": ("pass_cmp",),
    "2": ("pass_inc",),
    "3": ("pass_yd",),
    "4": ("pass_td",),
    "15": ("pass_td_40p",),
    "16": ("pass_td_50p",),
    "17": ("bonus_pass_yd_300",),
    "18": ("bonus_pass_yd_300", "bonus_pass_yd_400"),
    "19": ("pass_2pt",),
    "20": ("pass_int",),
    "23": ("rush_att",),
    "24": ("rush_yd",),
    "25": ("rush_td",),
    "26": ("rush_2pt",),
    "35": ("rush_td_40p",),
    "36": ("rush_td_50p",),
    "37": ("bonus_rush_yd_100",),
    "38": ("bonus_rush_yd_100", "bonus_rush_yd_200"),
    "42": ("rec_yd",),
    "43": ("rec_td",),
    "44": ("rec_2pt",),
    "45": ("rec_td_40p",),
    "46": ("rec_td_50p",),
    "53": ("rec",),
    "56": ("bonus_rec_yd_100",),
    "57": ("bonus_rec_yd_100", "bonus_rec_yd_200"),
    "58": ("rec_tgt",),
    "63": ("fum_rec_td",),
    "64": ("pass_sack",),
    "68": ("fum",),
    "72": ("fum_lost",),
    "77": ("fgm_40_49",),
    "79": ("fgmiss_40_49",),
    "80": ("fgm_30_39",),
    "82": ("fgmiss_30_39",),
    "83": ("fgm",),
    "84": ("fga",),
    "85": ("fgmiss",),
    "86": ("xpm",),
    "87": ("xpa",),
    "88": ("xpmiss",),
    "89": ("pts_allow_0",),
    "90": ("pts_allow_1_6",),
    "91": ("pts_allow_7_13",),
    "92": ("pts_allow_14_20",),
    "93": ("def_st_td",),
    "94": ("def_td",),
    "95": ("int",),
    "96": ("fum_rec",),
    "97": ("blk_kick",),
    "98": ("safe",),
    "99": ("sack",),
    "101": ("def_st_td",),
    "102": ("def_st_td",),
    "106": ("ff",),
    "107": ("tkl_ast",),
    "108": ("tkl_solo",),
    "109": ("tkl",),
    "113": ("pass_def",),
    "114": ("kr_yd",),
    "115": ("pr_yd",),
    "120": ("pts_allow",),
    "121": ("pts_allow_14_20",),
    "122": ("pts_allow_21_27",),
    "123": ("pts_allow_28_34",),
    "124": ("pts_allow_35p",),
    "125": ("pts_allow_35p",),
    "127": ("yds_allow",),
    "128": ("yds_allow_0_100",),
    "129": ("yds_allow_100_199",),
    "130": ("yds_allow_200_299",),
    "131": ("yds_allow_300_349",),
    "132": ("yds_allow_350_399",),
    "133": ("yds_allow_400_449",),
    "134": ("yds_allow_450_499",),
    "135": ("yds_allow_500_549",),
    "136": ("yds_allow_550p",),
    "187": ("pts_allow",),
    "188": ("pts_allow_0",),
    "189": ("pts_allow_1_6",),
    "190": ("pts_allow_7_13",),
    "191": ("pts_allow_14_20",),
    "192": ("pts_allow_14_20",),
    "193": ("pts_allow_21_27",),
    "194": ("pts_allow_28_34",),
    "195": ("pts_allow_35p",),
    "196": ("pts_allow_35p",),
    "198": ("fgm_50_59",),
    "200": ("fgmiss_50_59",),
    "201": ("fgm_60p",),
    "203": ("fgmiss_60p",),
    "210": ("gp",),
    "211": ("pass_fd",),
    "212": ("rush_fd",),
    "213": ("rec_fd",),
    "214": ("fgm_yds",),
}


def _normalized_name(name: str) -> str:
    without_suffix = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name.casefold())
    return re.sub(r"[^a-z0-9]", "", without_suffix)


def _projection_record(
    player: dict[str, Any], season: str, week: int | None
) -> dict[str, Any] | None:
    scoring_period = 0 if week is None else week
    split_type = 0 if week is None else 1
    return next(
        (
            record
            for record in player.get("stats") or []
            if isinstance(record, dict)
            and str(record.get("seasonId")) == str(season)
            and record.get("statSourceId") == 1
            and record.get("statSplitTypeId") == split_type
            and record.get("scoringPeriodId") == scoring_period
        ),
        None,
    )


def _normalized_stats(record: dict[str, Any]) -> dict[str, float]:
    raw_stats = record.get("stats")
    if not isinstance(raw_stats, dict):
        return {}

    normalized: dict[str, float] = {}
    for stat_id, value in raw_stats.items():
        if not isinstance(value, (int, float)):
            continue
        for sleeper_name in ESPN_STAT_MAP.get(str(stat_id), ()):
            normalized[sleeper_name] = normalized.get(sleeper_name, 0) + float(value)
    return normalized


# Match ESPN projection records to the corresponding Sleeper player IDs.
def map_projections_to_sleeper(
    projection_data: dict[str, Any],
    sleeper_players: dict[str, dict[str, Any]],
    season: str,
    week: int | None,
) -> dict[str, dict[str, float]]:
    sleeper_ids_by_espn_id = {
        str(player.get("espn_id")): str(player_id)
        for player_id, player in sleeper_players.items()
        if player.get("espn_id") not in (None, "")
    }
    sleeper_ids_by_identity: dict[tuple[str, str], str] = {}
    for player_id, player in sleeper_players.items():
        name = (
            f"{player.get('first_name') or ''} " f"{player.get('last_name') or ''}"
        ).strip()
        positions = {
            str(player.get("position") or ""),
            *(str(position) for position in player.get("fantasy_positions") or []),
        }
        for position in positions:
            sleeper_ids_by_identity[(_normalized_name(name), position)] = str(player_id)

    mapped: dict[str, dict[str, float]] = {}
    for entry in projection_data.get("players") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("player"), dict):
            continue
        player = entry["player"]
        position = ESPN_POSITION_MAP.get(player.get("defaultPositionId"), "")
        player_id = sleeper_ids_by_espn_id.get(str(player.get("id")))
        if position == "DEF":
            defense_id = ESPN_TEAM_MAP.get(player.get("proTeamId"))
            if defense_id in sleeper_players:
                player_id = defense_id
        if player_id is None:
            player_id = sleeper_ids_by_identity.get(
                (_normalized_name(str(player.get("fullName") or "")), position)
            )
        record = _projection_record(player, season, week)
        if player_id is not None and record is not None:
            mapped[player_id] = _normalized_stats(record)
    return mapped


# Fetch ESPN projections while preserving a local hourly JSON fallback.
class EspnClient:
    BASE_URL = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
        "seasons/{season}/segments/0/leaguedefaults/1"
    )
    SCOREBOARD_URL = (
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    )

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def get_nfl_projections(
        self,
        season: str,
        cache_path: Path,
        max_age: timedelta = timedelta(hours=1),
    ) -> dict[str, Any]:
        cached_data = self._read_cache(cache_path)
        if cached_data is not None:
            age_seconds = time.time() - cache_path.stat().st_mtime
            if age_seconds <= max_age.total_seconds():
                return cached_data

        try:
            response = requests.get(
                self.BASE_URL.format(season=season),
                params={"view": "kona_player_info"},
                headers={
                    "x-fantasy-filter": json.dumps(
                        {
                            "players": {
                                "limit": 5000,
                                "sortPercOwned": {
                                    "sortPriority": 1,
                                    "sortAsc": False,
                                },
                            }
                        }
                    )
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("players"), list):
                raise TypeError("ESPN projections response must contain players.")
        except (requests.RequestException, TypeError, ValueError):
            if cached_data is not None:
                return cached_data
            raise

        self._write_cache(cache_path, data)
        return data

    # Fetch exact ESPN game timestamps for one NFL week without reusing a cache.
    def get_nfl_schedule(
        self,
        season: str,
        week: int,
        season_type: str = "regular",
    ) -> dict[str, Any]:
        season_type_id = {"pre": 1, "regular": 2, "post": 3}[season_type]
        response = requests.get(
            self.SCOREBOARD_URL,
            params={
                "dates": season,
                "seasontype": season_type_id,
                "week": week,
                "limit": 100,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise TypeError("ESPN's schedule response must contain events.")
        return data

    @staticmethod
    def _read_cache(cache_path: Path) -> dict[str, Any] | None:
        if not cache_path.exists():
            return None
        try:
            with cache_path.open(encoding="utf-8") as cache_file:
                data = json.load(cache_file)
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _write_cache(cache_path: Path, data: dict[str, Any]) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=cache_path.parent,
                prefix=f".{cache_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                json.dump(data, temporary_file)
                temporary_path = Path(temporary_file.name)
            temporary_path.replace(cache_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

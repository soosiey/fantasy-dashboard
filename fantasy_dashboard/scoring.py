from enum import Enum


# Define the stable display sections used to organize Sleeper scoring keys.
class ScoringSection(str, Enum):
    PASSING = "Passing"
    RUSHING = "Rushing"
    RECEIVING = "Receiving"
    FUMBLES = "Fumbles"
    KICKING = "Kicking"
    DEFENSE = "Defense"
    SPECIAL_TEAMS = "Special Teams and Returns"
    IDP = "Individual Defensive Players"
    OTHER = "Other"


# Rank common scoring rules ahead of rare bonuses within each section.
_SCORING_SETTING_PRIORITY = {
    ScoringSection.PASSING: (
        "pass_yd",
        "pass_td",
        "pass_int",
        "pass_2pt",
        "pass_cmp",
        "pass_att",
        "pass_inc",
        "pass_sack",
        "pass_fd",
        "bonus_pass_yd_300",
        "bonus_pass_yd_400",
        "bonus_pass_cmp_25",
        "pass_td_40p",
        "pass_td_50p",
        "pass_cmp_40p",
        "pass_int_td",
        "bonus_fd_qb",
    ),
    ScoringSection.RUSHING: (
        "rush_yd",
        "rush_td",
        "rush_att",
        "rush_2pt",
        "rush_fd",
        "bonus_rush_yd_100",
        "bonus_rush_yd_200",
        "bonus_rush_rec_yd_100",
        "bonus_rush_rec_yd_200",
        "bonus_rush_att_20",
        "rush_40p",
        "rush_td_40p",
        "rush_td_50p",
        "bonus_rush_td_qb",
        "bonus_fd_rb",
    ),
    ScoringSection.RECEIVING: (
        "rec",
        "rec_yd",
        "rec_td",
        "rec_2pt",
        "rec_fd",
        "bonus_rec_yd_100",
        "bonus_rec_yd_200",
        "rec_40p",
        "rec_td_40p",
        "rec_td_50p",
        "rec_0_4",
        "rec_5_9",
        "rec_10_19",
        "rec_20_29",
        "rec_30_39",
        "bonus_rec_rb",
        "bonus_rec_wr",
        "bonus_rec_te",
        "bonus_fd_wr",
        "bonus_fd_te",
    ),
    ScoringSection.FUMBLES: ("fum_lost", "fum"),
    ScoringSection.KICKING: (
        "xpm",
        "xpmiss",
        "fgm",
        "fgm_yds",
        "fgm_yds_over_30",
        "fgm_0_19",
        "fgm_20_29",
        "fgm_30_39",
        "fgm_40_49",
        "fgm_50_59",
        "fgm_60p",
        "fgm_50p",
        "fgmiss",
        "fgmiss_0_19",
        "fgmiss_20_29",
        "fgmiss_30_39",
        "fgmiss_40_49",
        "fgmiss_50_59",
        "fgmiss_50p",
        "fgmiss_60p",
    ),
    ScoringSection.DEFENSE: (
        "def_td",
        "sack",
        "int",
        "fum_rec",
        "ff",
        "safe",
        "blk_kick",
        "def_2pt",
        "pts_allow_0",
        "pts_allow_1_6",
        "pts_allow_7_13",
        "pts_allow_14_20",
        "pts_allow_21_27",
        "pts_allow_28_34",
        "pts_allow_35p",
        "pts_allow",
        "yds_allow_0_100",
        "yds_allow_100_199",
        "yds_allow_200_299",
        "yds_allow_300_349",
        "yds_allow_350_399",
        "yds_allow_400_449",
        "yds_allow_450_499",
        "yds_allow_500_549",
        "yds_allow_550p",
        "yds_allow",
        "def_pass_def",
        "def_forced_punts",
        "def_3_and_out",
        "def_4_and_stop",
        "qb_hit",
        "tkl_solo",
        "tkl_ast",
        "tkl",
        "tkl_loss",
        "sack_yd",
        "bonus_sack_2p",
        "bonus_tkl_10p",
        "bonus_def_int_td_50p",
        "bonus_def_fum_td_50p",
    ),
    ScoringSection.SPECIAL_TEAMS: (
        "def_st_td",
        "st_td",
        "def_st_fum_rec",
        "st_fum_rec",
        "def_st_ff",
        "st_ff",
        "kr_yd",
        "pr_yd",
        "def_kr_yd",
        "def_pr_yd",
        "int_ret_yd",
        "fum_ret_yd",
        "fg_ret_yd",
        "blk_kick_ret_yd",
        "st_tkl_solo",
        "def_st_tkl_solo",
    ),
    ScoringSection.IDP: (
        "idp_tkl_solo",
        "idp_tkl_ast",
        "idp_tkl",
        "idp_tkl_loss",
        "idp_sack",
        "idp_int",
        "idp_ff",
        "idp_fum_rec",
        "idp_pass_def",
        "idp_qb_hit",
        "idp_safe",
        "idp_blk_kick",
        "idp_def_td",
        "idp_sack_yd",
        "idp_int_ret_yd",
        "idp_fum_ret_yd",
        "idp_pass_def_3p",
    ),
}


# Classify known key patterns while retaining unfamiliar API keys under Other.
def get_scoring_section(setting: str) -> ScoringSection:
    if setting.startswith("idp_"):
        return ScoringSection.IDP
    if setting.startswith(("st_", "def_st_", "def_kr_", "def_pr_")) or setting in {
        "blk_kick_ret_yd",
        "fg_ret_yd",
        "fum_ret_yd",
        "int_ret_yd",
        "kr_yd",
        "pr_yd",
    }:
        return ScoringSection.SPECIAL_TEAMS
    if setting.startswith(("pass_", "bonus_pass_", "bonus_fd_qb")):
        return ScoringSection.PASSING
    if setting.startswith(("rush_", "bonus_rush_", "bonus_fd_rb")):
        return ScoringSection.RUSHING
    if setting == "rec" or setting.startswith(
        ("rec_", "bonus_rec_", "bonus_fd_te", "bonus_fd_wr")
    ):
        return ScoringSection.RECEIVING
    if setting in {"fum", "fum_lost"}:
        return ScoringSection.FUMBLES
    if setting.startswith(("fgm", "fgmiss", "xpm")):
        return ScoringSection.KICKING
    if setting.startswith(
        (
            "def_",
            "pts_allow",
            "yds_allow",
            "bonus_def_",
            "bonus_sack_",
            "bonus_tkl_",
        )
    ) or setting in {
        "blk_kick",
        "ff",
        "fum_rec",
        "fum_rec_td",
        "int",
        "qb_hit",
        "sack",
        "sack_yd",
        "safe",
        "tkl",
        "tkl_ast",
        "tkl_loss",
        "tkl_solo",
    }:
        return ScoringSection.DEFENSE
    return ScoringSection.OTHER


# Sort recognized rules by relevance and unknown rules alphabetically afterward.
def get_scoring_sort_key(section: ScoringSection, setting: str) -> tuple[int, str]:
    priorities = _SCORING_SETTING_PRIORITY.get(section, ())
    try:
        return priorities.index(setting), setting
    except ValueError:
        return len(priorities), setting

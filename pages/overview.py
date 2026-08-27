from dataclasses import fields

import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient


SCORING_SECTIONS = (
    "Passing",
    "Rushing",
    "Receiving",
    "Fumbles",
    "Kicking",
    "Defense",
    "Special Teams and Returns",
    "Individual Defensive Players",
    "Other",
)

SCORING_SETTING_PRIORITY = {
    "Passing": (
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
    "Rushing": (
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
    "Receiving": (
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
        "bonus_fd_rb",
        "bonus_fd_wr",
        "bonus_fd_te",
    ),
    "Fumbles": ("fum_lost", "fum", "fum_rec", "fum_rec_td"),
    "Kicking": (
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
    "Defense": (
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
    "Special Teams and Returns": (
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
    "Individual Defensive Players": (
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


def get_scoring_section(setting: str) -> str:
    if setting.startswith("idp_"):
        return "Individual Defensive Players"
    if setting.startswith(("st_", "def_st_", "def_kr_", "def_pr_")) or setting in {
        "blk_kick_ret_yd",
        "fg_ret_yd",
        "fum_ret_yd",
        "int_ret_yd",
        "kr_yd",
        "pr_yd",
    }:
        return "Special Teams and Returns"
    if setting.startswith(("pass_", "bonus_pass_", "bonus_fd_qb")):
        return "Passing"
    if setting.startswith(("rush_", "bonus_rush_", "bonus_fd_rb")):
        return "Rushing"
    if setting == "rec" or setting.startswith(
        ("rec_", "bonus_rec_", "bonus_fd_te", "bonus_fd_wr")
    ):
        return "Receiving"
    if setting in {"fum", "fum_lost"}:
        return "Fumbles"
    if setting.startswith(("fgm", "fgmiss", "xpm")):
        return "Kicking"
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
        return "Defense"
    return "Other"


def get_scoring_sort_key(section: str, setting: str) -> tuple[int, str]:
    priorities = SCORING_SETTING_PRIORITY.get(section, ())
    try:
        return priorities.index(setting), setting
    except ValueError:
        return len(priorities), setting


if "client" not in st.session_state:
    client = SleeperClient()
else:
    client = st.session_state.get("client")

league_id = st.query_params.get("league_id")

if league_id is not None:
    st.session_state["league_id"] = str(league_id)
else:
    league_id = st.session_state["league_id"]

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

st.title("Overview")
league = client.get_single_league(league_id)
st.write(f"League: {league.name}")

teams_tab, settings_tab = st.tabs(["Teams", "Settings"])

with teams_tab:
    st.write("Players: ")
    teams = client.get_all_users(league_id)
    players_list = []
    images_list = []
    for team in teams.users:
        display_name = team.display_name
        team_name = team.team_name
        if team_name == "None":
            continue
        image = client.get_avatar(team.avatar_id)
        st.write(team_name)
        st.image(image, caption=display_name)
        st.page_link("pages/team.py", label="View Team", query_params={"user_id": team.user_id})

with settings_tab:
    league_settings_tab, scoring_settings_tab = st.tabs(
        ["League Settings", "Scoring Settings"]
    )

    with league_settings_tab:
        for setting in fields(league.settings):
            label = setting.name.replace("_", " ").title()
            st.write(f"**{label}:** {getattr(league.settings, setting.name)}")

    with scoring_settings_tab:
        grouped_scoring_settings = {section: [] for section in SCORING_SECTIONS}
        for setting, value in league.scoring_settings.items():
            section = get_scoring_section(setting)
            grouped_scoring_settings[section].append((setting, value))

        for section, section_settings in grouped_scoring_settings.items():
            if not section_settings:
                continue
            st.subheader(section)
            for setting, value in sorted(
                section_settings,
                key=lambda item: get_scoring_sort_key(section, item[0]),
            ):
                label = setting.replace("_", " ").title()
                st.write(f"**{label}:** {value}")

with st.bottom:
    league_change = st.button("Switch Leagues")
    reset = st.button("Log Out")

if league_change:
    st.session_state.pop("league_id")
    if "league_id" in st.query_params:
        st.query_params.pop("league_id")
    st.switch_page("pages/leagues.py")
if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

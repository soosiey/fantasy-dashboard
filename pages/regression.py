import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.data import (
    get_league,
    get_league_users,
    get_nfl_players,
    get_player_stats,
    get_projected_player_stats,
    get_rosters,
)
from fantasy_dashboard.player_regression import (
    FEATURE_NAMES,
    RegressionReport,
    build_regression_observations,
    run_ridge_regression_evaluation,
)
from fantasy_dashboard.player_stats import (
    build_player_identity_image,
    build_player_roster_labels,
)
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    require_authentication,
    resolve_league_id,
)

TRAINING_SEASON = 2024
EVALUATION_SEASON = 2025
HISTORICAL_WEEKS = range(1, 19)


@st.cache_data(
    max_entries=8,
    show_spinner="Training and evaluating residual models...",
)
def _build_regression_report(
    actuals_by_season_week: dict,
    projections_by_season_week: dict,
    player_positions: dict,
    scoring_settings: dict,
) -> RegressionReport:
    observations = build_regression_observations(
        actuals_by_season_week,
        projections_by_season_week,
        player_positions,
        scoring_settings,
    )
    return run_ridge_regression_evaluation(
        observations,
        training_season=TRAINING_SEASON,
        evaluation_season=EVALUATION_SEASON,
    )


def _player_name(player: dict) -> str:
    name = " ".join(
        part
        for part in (
            str(player.get("first_name") or "").strip(),
            str(player.get("last_name") or "").strip(),
        )
        if part
    )
    return name or str(player.get("full_name") or "Unknown Player")


require_authentication("regression")
league_id = resolve_league_id()
if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")
if not st.session_state.get(ANALYSIS_MODE_KEY):
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.rerun()

st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 95rem; }</style>",
    unsafe_allow_html=True,
)
st.title("Regression")
st.caption(
    "Ridge regression adjusts ESPN's projected fantasy points by predicting each "
    "player-week residual. Models are tuned chronologically on 2024 and evaluated "
    "sequentially on 2025."
)

league = get_league(league_id)
players = get_nfl_players()
rosters = get_rosters(league_id)
teams = get_league_users(league_id)
actuals_by_season_week = {}
projections_by_season_week = {}
unavailable_inputs = []
for season in (TRAINING_SEASON, EVALUATION_SEASON):
    actuals_by_season_week[season] = {}
    projections_by_season_week[season] = {}
    for week in HISTORICAL_WEEKS:
        try:
            actuals_by_season_week[season][week] = get_player_stats(
                str(season), "regular", week
            )
            projections_by_season_week[season][week] = get_projected_player_stats(
                str(season), week
            )
        except (OSError, requests.RequestException, TypeError, ValueError):
            unavailable_inputs.append((season, week))

if unavailable_inputs:
    unavailable_label = ", ".join(
        f"{season} Week {week}" for season, week in unavailable_inputs
    )
    st.warning(f"Historical inputs were unavailable for: {unavailable_label}.")

player_positions = {
    player_id: {"position": player.get("position")}
    for player_id, player in players.items()
}
report = _build_regression_report(
    actuals_by_season_week,
    projections_by_season_week,
    player_positions,
    league.scoring_settings,
)
st.caption(
    "Regression results are cached and retrained only when the historical inputs, "
    "player positions, league scoring settings, or model implementation change."
)

overall = next(
    (evaluation for evaluation in report.evaluations if evaluation.position == "Overall"),
    None,
)
if overall is None:
    st.info("There are not enough matched historical player-weeks to evaluate the model.")
else:
    metric_columns = st.columns(4)
    metric_columns[0].metric("Evaluation player-weeks", f"{overall.observations:,}")
    metric_columns[1].metric("ESPN MAE", f"{overall.provider_mae:.2f}")
    metric_columns[2].metric(
        "Ridge MAE",
        f"{overall.model_mae:.2f}",
        delta=f"{overall.provider_mae - overall.model_mae:+.2f} points",
    )
    metric_columns[3].metric(
        "MAE improvement",
        f"{overall.mae_improvement:.1%}",
    )

evaluation_tab, players_tab, coefficients_tab = st.tabs(
    ["Evaluation", "Players", "Coefficients"]
)
with evaluation_tab:
    if report.evaluations:
        evaluation_frame = pd.DataFrame(
            [
                {
                    "Position": evaluation.position,
                    "Player-Weeks": evaluation.observations,
                    "Ridge Alpha": evaluation.alpha if evaluation.position != "Overall" else None,
                    "ESPN MAE": evaluation.provider_mae,
                    "Ridge MAE": evaluation.model_mae,
                    "MAE Improvement": evaluation.mae_improvement,
                    "ESPN RMSE": evaluation.provider_rmse,
                    "Ridge RMSE": evaluation.model_rmse,
                    "ESPN Bias": evaluation.provider_bias,
                    "Ridge Bias": evaluation.model_bias,
                    "Ridge R²": evaluation.model_r_squared,
                }
                for evaluation in report.evaluations
            ]
        )
        st.dataframe(
            evaluation_frame,
            hide_index=True,
            width="stretch",
            column_config={
                "Position": st.column_config.TextColumn(width="small"),
                "Player-Weeks": st.column_config.NumberColumn(format="%d"),
                "Ridge Alpha": st.column_config.NumberColumn(format="%.1f"),
                "ESPN MAE": st.column_config.NumberColumn(format="%.2f"),
                "Ridge MAE": st.column_config.NumberColumn(format="%.2f"),
                "MAE Improvement": st.column_config.NumberColumn(format="percent"),
                "ESPN RMSE": st.column_config.NumberColumn(format="%.2f"),
                "Ridge RMSE": st.column_config.NumberColumn(format="%.2f"),
                "ESPN Bias": st.column_config.NumberColumn(format="%+.2f"),
                "Ridge Bias": st.column_config.NumberColumn(format="%+.2f"),
                "Ridge R²": st.column_config.NumberColumn(format="%.3f"),
            },
        )
    st.markdown(
        "Positive bias means players scored more than projected. Improvement is "
        "measured against the original ESPN projection on the same 2025 player-weeks."
    )

with players_tab:
    filter_columns = st.columns(3)
    with filter_columns[0]:
        position_filter = st.selectbox(
            "Position",
            ["All Positions", *sorted(report.final_models)],
            key=f"regression-position-{league_id}",
        )
    with filter_columns[1]:
        minimum_games = st.slider(
            "Minimum evaluated games",
            1,
            18,
            4,
            key=f"regression-minimum-games-{league_id}",
        )
    with filter_columns[2]:
        player_search = st.text_input(
            "Player name",
            placeholder="Search by player name",
            key=f"regression-player-search-{league_id}",
        )

    roster_labels = build_player_roster_labels(rosters.rosters, teams.users)
    player_rows = []
    search_query = player_search.strip().casefold()
    for summary in report.player_summaries:
        player = players.get(summary.player_id, {})
        name = _player_name(player)
        if position_filter != "All Positions" and summary.position != position_filter:
            continue
        if summary.observations < minimum_games:
            continue
        if search_query and search_query not in name.casefold():
            continue
        player_rows.append(
            {
                "Player ID": summary.player_id,
                "Player": build_player_identity_image(
                    name, roster_labels.get(summary.player_id, "")
                ),
                "Position": summary.position,
                "Games": summary.observations,
                "Actual Avg": summary.actual_average,
                "ESPN Avg": summary.provider_average,
                "ESPN Residual": summary.provider_residual_average,
                "Ridge Adjustment": summary.adjustment_average,
                "Adjusted Avg": summary.adjusted_average,
                "Model Residual": summary.model_residual_average,
                "ESPN MAE": summary.provider_mae,
                "Ridge MAE": summary.model_mae,
                "MAE Improvement": summary.mae_improvement,
            }
        )
    st.caption(f"{len(player_rows):,} players match the selected filters.")
    if not player_rows:
        st.info("No evaluated players match the selected filters.")
    else:
        player_frame = pd.DataFrame(player_rows).sort_values(
            ["Games", "Ridge MAE"], ascending=[False, True]
        )
        st.dataframe(
            player_frame,
            hide_index=True,
            height=700,
            width="stretch",
            column_config={
                "Player ID": None,
                "Player": st.column_config.ImageColumn(width=260),
                "Position": st.column_config.TextColumn("Pos", width="small"),
                "Games": st.column_config.NumberColumn(format="%d"),
                "Actual Avg": st.column_config.NumberColumn(format="%.2f"),
                "ESPN Avg": st.column_config.NumberColumn(format="%.2f"),
                "ESPN Residual": st.column_config.NumberColumn(format="%+.2f"),
                "Ridge Adjustment": st.column_config.NumberColumn(format="%+.2f"),
                "Adjusted Avg": st.column_config.NumberColumn(format="%.2f"),
                "Model Residual": st.column_config.NumberColumn(format="%+.2f"),
                "ESPN MAE": st.column_config.NumberColumn(format="%.2f"),
                "Ridge MAE": st.column_config.NumberColumn(format="%.2f"),
                "MAE Improvement": st.column_config.NumberColumn(format="percent"),
            },
        )

with coefficients_tab:
    coefficient_rows = []
    for position, model in report.final_models.items():
        for feature, coefficient in zip(FEATURE_NAMES, model.coefficients):
            coefficient_rows.append(
                {
                    "Position": position,
                    "Feature": feature,
                    "Standardized Coefficient": coefficient,
                    "Ridge Alpha": model.alpha,
                    "Training Player-Weeks": model.observations,
                }
            )
    if coefficient_rows:
        st.dataframe(
            pd.DataFrame(coefficient_rows),
            hide_index=True,
            width="stretch",
            column_config={
                "Position": st.column_config.TextColumn(width="small"),
                "Feature": st.column_config.TextColumn(width="large"),
                "Standardized Coefficient": st.column_config.NumberColumn(
                    format="%+.3f"
                ),
                "Ridge Alpha": st.column_config.NumberColumn(format="%.1f"),
                "Training Player-Weeks": st.column_config.NumberColumn(format="%d"),
            },
        )
        st.caption(
            "Each coefficient is the predicted fantasy-point residual change for a "
            "one-standard-deviation increase in that feature, holding the other "
            "features fixed."
        )

with st.expander("Method and interpretation"):
    st.markdown(
        r"""
        The target is the provider residual:

        $$e_{i,t}=Y_{i,t}-P_{i,t}$$

        The adjusted forecast is:

        $$\widehat{Y}_{i,t}=\max(0,P_{i,t}+\widehat{e}_{i,t})$$

        Separate models are fitted for QB, RB, WR, TE, K, and DEF. Features use
        only the current ESPN projection and actual or residual history from prior
        weeks in the same season. Ridge penalties are selected through rolling
        2024 validation. For 2025 evaluation, each week is predicted before its
        results are added to the next week's training set.

        The evaluation is conditional on recording a game and receiving a positive
        ESPN projection. It does not yet estimate the separate probability that a
        player is inactive. Historical ESPN records are provider-labeled weekly
        projections retrieved retrospectively rather than locally timestamped
        pregame captures.
        """
    )

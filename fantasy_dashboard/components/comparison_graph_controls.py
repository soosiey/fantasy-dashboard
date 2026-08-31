from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True, slots=True)
class ComparisonGraphSettings:
    hit_tolerance: float = 3.0
    consistency_band_percent: float = 20.0
    boom_bust_tolerance: float = 3.0


def render_comparison_graph_settings(
    selected_options: list[dict[str, str]],
    *,
    key_prefix: str,
) -> ComparisonGraphSettings:
    """Render only the settings used by the selected metric categories."""
    selected_categories = {option["category"] for option in selected_options}
    show_accuracy = "Projection Accuracy" in selected_categories
    show_consistency = "Consistency" in selected_categories
    if not show_accuracy and not show_consistency:
        return ComparisonGraphSettings()

    control_count = int(show_accuracy) + (2 * int(show_consistency))
    columns = st.columns(control_count)
    column_index = 0
    hit_tolerance = 3.0
    consistency_band = 20.0
    boom_bust_tolerance = 3.0

    if show_accuracy:
        with columns[column_index]:
            hit_tolerance = st.number_input(
                "Hit tolerance",
                min_value=0.0,
                value=3.0,
                step=0.5,
                key=f"{key_prefix}-hit-tolerance",
                help=(
                    "A projection is a hit when it is within this many units "
                    "of the actual result."
                ),
            )
        column_index += 1

    if show_consistency:
        with columns[column_index]:
            consistency_band = st.number_input(
                "Consistency band (%)",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                step=5.0,
                key=f"{key_prefix}-consistency-band",
                help="Games within this percentage of the season average count.",
            )
        with columns[column_index + 1]:
            boom_bust_tolerance = st.number_input(
                "Boom/bust tolerance",
                min_value=0.0,
                value=3.0,
                step=0.5,
                key=f"{key_prefix}-boom-bust-tolerance",
                help=(
                    "The amount by which actual production must beat or miss "
                    "the projection."
                ),
            )

    return ComparisonGraphSettings(
        hit_tolerance=float(hit_tolerance),
        consistency_band_percent=float(consistency_band),
        boom_bust_tolerance=float(boom_bust_tolerance),
    )

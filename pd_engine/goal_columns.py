"""Maps internal goal keys to exact CSV column names (GOALS - LAWNS / GARDENS / FARMS)."""

from __future__ import annotations

# Lawn goals (CSV row 2 after "App positioning")
LAWN_GOAL_COLS: dict[str, str] = {
    "deep_green_colour": "Deep green colour",
    "thickening_and_density": "Thickening and density",
    "fast_recovery_from_stress": "Fast recovery from stress",
    "weed_suppression_through_dominance": "Weed suppression through dominance",
    "low_maintenance_resilience": "Low maintenance resilience",
}

# Garden goals
GARDEN_GOAL_COLS: dict[str, str] = {
    "strong_flowering_and_fruiting": "Strong flowering and fruiting performance",
    "improved_soil_fertility": "Improved soil fertility over time",
    "root_development_transplant": "Root development and transplant success",
    "pest_and_disease_resilience": "Pest and disease resilience",
    "consistent_growth_across_seasons": "Consistent growth across seasons",
}

# Farm goals
FARM_GOAL_COLS: dict[str, str] = {
    "yield_increase": "Yield increase",
    "soil_efficiency": "Soil efficiency",
    "water_efficiency": "Water efficiency",
    "crop_uniformity": "Crop uniformity",
    "reduced_input_dependency": "Reduced input dependency over time",
}

GoalVertical = str  # "lawn" | "garden" | "farm"

ALL_GOAL_KEYS = frozenset(
    list(LAWN_GOAL_COLS) + list(GARDEN_GOAL_COLS) + list(FARM_GOAL_COLS)
)


def goal_columns_for_vertical(vertical: str) -> dict[str, str]:
    if vertical == "lawn":
        return LAWN_GOAL_COLS
    if vertical == "garden":
        return GARDEN_GOAL_COLS
    if vertical == "farm":
        return FARM_GOAL_COLS
    return {}

"""
Goal weighting as a multiplier layer on top of the product scoring engine.

- Each vertical (lawn / garden / farm) has default priorities reflecting different
  definitions of success.
- Intent scales those priorities (rescue vs performance vs diagnosis, etc.).
- Selected user goals gate which keys apply; effective weights are normalized and
  capped so no single goal dominates beyond MAX_SINGLE_GOAL_SHARE.
- Complementary goal pairs add a small synergy bump when both are selected and
  the product scores well on both.
"""

from __future__ import annotations

from .goal_columns import ALL_GOAL_KEYS, FARM_GOAL_COLS, GARDEN_GOAL_COLS, LAWN_GOAL_COLS
from .types import GoalVertical, Intent, Product, UserInput

# Priorities per vertical (sum ≈ 1.0) — “what success means” by system
DEFAULT_PRIORITY_LAWN: dict[str, float] = {
    "deep_green_colour": 0.18,
    "thickening_and_density": 0.28,
    "fast_recovery_from_stress": 0.22,
    "weed_suppression_through_dominance": 0.16,
    "low_maintenance_resilience": 0.16,
}

DEFAULT_PRIORITY_GARDEN: dict[str, float] = {
    "strong_flowering_and_fruiting": 0.18,
    "improved_soil_fertility": 0.28,
    "root_development_transplant": 0.26,
    "pest_and_disease_resilience": 0.14,
    "consistent_growth_across_seasons": 0.14,
}

DEFAULT_PRIORITY_FARM: dict[str, float] = {
    "yield_increase": 0.22,
    "soil_efficiency": 0.28,
    "water_efficiency": 0.20,
    "crop_uniformity": 0.16,
    "reduced_input_dependency": 0.14,
}


def _priorities(vertical: GoalVertical) -> dict[str, float]:
    if vertical == "lawn":
        return dict(DEFAULT_PRIORITY_LAWN)
    if vertical == "garden":
        return dict(DEFAULT_PRIORITY_GARDEN)
    if vertical == "farm":
        return dict(DEFAULT_PRIORITY_FARM)
    return {}


# Intent modifies emphasis on each goal key (1.0 = neutral)
def _intent_goal_factors(intent: Intent, vertical: GoalVertical) -> dict[str, float]:
    keys = list(LAWN_GOAL_COLS) + list(GARDEN_GOAL_COLS) + list(FARM_GOAL_COLS)
    f = {k: 1.0 for k in keys}

    if intent == "rescue_mode":
        for k in [
            "fast_recovery_from_stress",
            "improved_soil_fertility",
            "root_development_transplant",
            "water_efficiency",
            "soil_efficiency",
        ]:
            f[k] = 1.38
        f["deep_green_colour"] = 0.72
        f["crop_uniformity"] = 0.85

    elif intent == "establishment_mode":
        for k in [
            "root_development_transplant",
            "improved_soil_fertility",
            "thickening_and_density",
            "soil_efficiency",
            "yield_increase",
        ]:
            f[k] = 1.32
        f["deep_green_colour"] = 0.88

    elif intent == "performance_mode":
        for k in [
            "deep_green_colour",
            "thickening_and_density",
            "yield_increase",
            "crop_uniformity",
            "strong_flowering_and_fruiting",
        ]:
            f[k] = 1.28
        f["low_maintenance_resilience"] = 0.9

    elif intent == "diagnosis_mode":
        for k in [
            "improved_soil_fertility",
            "pest_and_disease_resilience",
            "soil_efficiency",
            "fast_recovery_from_stress",
            "consistent_growth_across_seasons",
        ]:
            f[k] = 1.25
        f["deep_green_colour"] = 0.85

    else:  # maintenance_mode
        for k in ["low_maintenance_resilience", "consistent_growth_across_seasons", "weed_suppression_through_dominance"]:
            f[k] = 1.08

    # Vertical-specific nudges so intent doesn’t fight the domain
    if vertical == "lawn" and intent == "rescue_mode":
        f["fast_recovery_from_stress"] *= 1.12
        f["thickening_and_density"] *= 1.08
    if vertical == "garden" and intent == "diagnosis_mode":
        f["improved_soil_fertility"] *= 1.1
        f["root_development_transplant"] *= 1.08
    if vertical == "farm" and intent == "performance_mode":
        f["yield_increase"] *= 1.12
        f["crop_uniformity"] *= 1.08

    return f


MAX_SINGLE_GOAL_SHARE = 0.42  # no single goal > 42% of effective weight mass

# Pairs of goal keys that synergise when selected together (complementary outcomes)
GOAL_PAIR_SYNERGY: list[tuple[str, str, float]] = [
    ("root_development_transplant", "improved_soil_fertility", 0.06),
    ("water_efficiency", "soil_efficiency", 0.07),
    ("thickening_and_density", "deep_green_colour", 0.05),
    ("weed_suppression_through_dominance", "thickening_and_density", 0.04),
]


def _goal_scores_dict(product: Product, vertical: GoalVertical) -> dict[str, float]:
    if vertical == "lawn":
        return product.lawn_goal_scores
    if vertical == "garden":
        return product.garden_goal_scores
    if vertical == "farm":
        return product.farm_goal_scores
    return {}


_GOAL_SELECTED = 0.35


def majority_keep_it_healthy_goals(user: UserInput) -> bool:
    """True when more than half of the current 'What do you want?' goals are selected."""
    if user.recommendation_mode != "goals" or not user.goal_vertical:
        return False
    keys = list(_priorities(user.goal_vertical))
    if not keys:
        return False
    selected = sum(
        1 for k in keys if float(user.goal_weights.get(k, 0.0)) >= _GOAL_SELECTED
    )
    return selected * 2 > len(keys)


def effective_goal_weights(user: UserInput) -> dict[str, float]:
    """Selected goals × default vertical priorities × intent factors → normalized capped weights."""
    if user.recommendation_mode != "goals" or not user.goal_vertical or not user.goal_weights:
        return {}

    v = user.goal_vertical
    pri = _priorities(v)
    igf = _intent_goal_factors(user.intent, v)

    raw: dict[str, float] = {}
    for k, sel in user.goal_weights.items():
        if k not in ALL_GOAL_KEYS or float(sel) <= 0:
            continue
        base = pri.get(k, 0.2)
        raw[k] = float(sel) * base * igf.get(k, 1.0)

    s = sum(raw.values())
    if s <= 0:
        return {}

    out = {k: v / s for k, v in raw.items()}

    # Cap dominant weight and renormalize (iterative clip)
    for _ in range(3):
        max_k = max(out, key=lambda x: out[x])
        if out[max_k] <= MAX_SINGLE_GOAL_SHARE:
            break
        excess = out[max_k] - MAX_SINGLE_GOAL_SHARE
        out[max_k] = MAX_SINGLE_GOAL_SHARE
        others = [k for k in out if k != max_k]
        if not others:
            break
        add_each = excess / len(others)
        for k in others:
            out[k] += add_each
        t = sum(out.values())
        out = {k: v / t for k, v in out.items()}

    return out


def goal_pair_synergy_bonus(product: Product, vertical: GoalVertical, eff_w: dict[str, float]) -> float:
    if not eff_w:
        return 0.0
    gdict = _goal_scores_dict(product, vertical)
    bonus = 0.0
    for a, b, mag in GOAL_PAIR_SYNERGY:
        if a not in eff_w or b not in eff_w:
            continue
        sa = float(gdict.get(a, 0.0))
        sb = float(gdict.get(b, 0.0))
        if sa >= 3.0 and sb >= 3.0:
            bonus += mag * min(eff_w[a], eff_w[b]) * 2.0  # scale with co-selection strength
    return min(bonus, 0.18)


def goal_alignment_01(
    product: Product,
    vertical: GoalVertical,
    eff_w: dict[str, float],
) -> tuple[float, float]:
    """
    Returns (alignment_0_1, raw_weighted_avg_0_5).
    alignment is in [0,1] for use in multipliers.
    """
    gdict = _goal_scores_dict(product, vertical)
    if not eff_w:
        return 0.0, 0.0

    num = 0.0
    den = 0.0
    for k, w in eff_w.items():
        den += w
        num += w * float(gdict.get(k, 0.0))
    if den <= 0:
        return 0.0, 0.0
    raw_avg = num / den  # 0..5 typically
    alignment = raw_avg / 5.0
    return max(0.0, min(1.0, alignment)), raw_avg


def goal_multiplier(alignment_01: float, intent: Intent) -> float:
    """
    Maps goal fit [0,1] to a multiplier band; intent slightly widens/narrows the band.
    """
    lo, hi = 0.94, 1.28
    if intent == "rescue_mode":
        lo, hi = 0.96, 1.26
    return lo + (hi - lo) * alignment_01

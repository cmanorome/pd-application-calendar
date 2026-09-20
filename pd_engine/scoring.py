from __future__ import annotations

from dataclasses import dataclass

from .constraints import is_gardenish, is_lawnish
from .goal_layer import (
    effective_goal_weights,
    goal_alignment_01,
    goal_multiplier,
    goal_pair_synergy_bonus,
)
from .types import (
    Product,
    RoleType,
    ScoredProduct,
    Season,
    UserInput,
)


@dataclass(frozen=True)
class Weights:
    problem: float = 1.4
    soil: float = 0.9
    use_case: float = 0.85
    goal_segment: float = 1.2
    seasonal: float = 0.15
    synergy: float = 0.08


def role_multiplier(role: RoleType, *, user: UserInput) -> float:
    yellowing = float(user.problems.get("yellowing", 0.0))
    lockout = float(user.problems.get("nutrient_lockout", 0.0))
    slow = float(user.problems.get("slow_growth", 0.0))
    acidic = float(user.soils.get("acidic", 0.0))
    alkaline = float(user.soils.get("alkaline", 0.0))
    chemistry_needed = acidic >= 0.35 or alkaline >= 0.35 or lockout >= 0.5

    if role == RoleType.SOIL_STRUCTURE:
        return 1.30 if user.intent != "maintenance_mode" else 1.22
    if role == RoleType.SOIL_CHEMISTRY:
        return 1.28 if chemistry_needed else 1.05
    if role == RoleType.BIOLOGY:
        return 1.20
    if role == RoleType.UPTAKE:
        return 1.15
    if role == RoleType.NUTRITION:
        if user.recommendation_mode == "goals":
            return 1.12
        if slow >= 0.5 and lockout < 0.5:
            return 1.25
        return 0.95
    if role == RoleType.VISUAL:
        return 1.20 if yellowing >= 0.5 else 0.70
    if role == RoleType.BUNDLE:
        return 1.10
    return 1.0


def _dot01(user: dict[str, float], prod: dict[str, float]) -> float:
    # user weights are 0..1. prod are typically 0..5 or 1..3; normalize per-key.
    total = 0.0
    denom = 0.0
    for k, w in user.items():
        if w <= 0:
            continue
        denom += w
        total += w * float(prod.get(k, 0.0))
    if denom <= 0:
        return 0.0
    return total / denom


def _goal_scores_for_product(product: Product, vertical: str | None) -> dict[str, float]:
    if vertical == "lawn":
        return product.lawn_goal_scores
    if vertical == "garden":
        return product.garden_goal_scores
    if vertical == "farm":
        return product.farm_goal_scores
    return {}


def _garden_stage_alignment_bonus(product: Product, user: UserInput) -> tuple[float, str | None]:
    """
    Nudge named garden lines (FFR vs RSL) so stage/intent matches real use:
    establishment + root development favours the vegetative / planting line (RSL)
    over reproductive formulations (FFR), even when flowering is also ticked.
    """
    if user.recommendation_mode != "goals" or user.goal_vertical != "garden":
        return 0.0, None
    blob = f"{product.name} {product.category}".lower()

    wf = float(user.goal_weights.get("strong_flowering_and_fruiting", 0.0))
    wr = float(user.goal_weights.get("root_development_transplant", 0.0))
    has_ff = wf >= 0.35
    has_root = wr >= 0.35

    def _ffr_line() -> bool:
        if product.id in ("575", "721"):
            return True
        return "flowers" in blob and "fruit" in blob

    def _rsl_line() -> bool:
        if product.id == "1156":
            return True
        return "roots, shoots" in blob and "leaves" in blob

    # Planting / establishment: vegetative & roots over flower/fruit SKUs when root goal is on
    if user.intent == "establishment_mode" and has_root:
        if _rsl_line():
            return (
                0.45,
                "Establishment / planting — Roots, Shoots & Leaves line (vegetative growth & roots)",
            )
        if has_ff and _ffr_line():
            return (
                0.12,
                "Flower/fruit formulation de-emphasised during establishment when root goal is active",
            )

    if has_ff and _ffr_line():
        return 0.40, "Flowering/fruiting stage product (aligned with selected garden goal)"

    if has_root and _rsl_line():
        return 0.35, "Root establishment / vegetative line (aligned with selected garden goal)"

    return 0.0, None


def _core_range_bonus(product: Product, user: UserInput) -> float:
    """Lawn Lovers Starter/Pro SKUs are the default range we recommend most."""
    if not product.is_core_range:
        return 0.0
    if is_gardenish(user):
        # Activ8EXTRA is the lawn pack feed; garden keeps Activ8Mate / RSL / FFR.
        if product.id == "A8X":
            return 0.0
        return 0.25
    if is_lawnish(user) or user.use_case is None:
        return 0.42
    return 0.22


def _context_fit(product: Product, user: UserInput) -> float:
    """Keep lawn primary, but stop turf SKUs crowding out garden lines (and vice versa)."""
    lawn_uc = float(product.use_case_scores.get("lawn", 0.0))
    garden_uc = max(
        float(product.use_case_scores.get("garden_beds", 0.0)),
        float(product.use_case_scores.get("pots", 0.0)),
        float(product.use_case_scores.get("indoor_plants", 0.0)),
    )
    if is_gardenish(user):
        if product.is_lawn_specialist:
            return -1.0
        if product.is_garden_specialist or product.is_garden_reproductive:
            return 0.55
        if product.id == "A8M":
            return 0.35
        if product.id == "A8X":
            return -0.12
        return 0.0
    if is_lawnish(user):
        if lawn_uc <= 0 and garden_uc > 0:
            return -0.55
    return 0.0


def score_product(product: Product, user: UserInput, *, weights: Weights) -> ScoredProduct:
    problem_match = _dot01(user.problems, product.problem_scores)  # 0..5-ish
    soil_match = _dot01(user.soils, product.soil_scores)  # 0..3-ish
    use_case_match = 0.0
    if user.use_case:
        use_case_match = float(product.use_case_scores.get(user.use_case, 0.0))  # 0..1

    goal_match = 0.0  # weighted CSV fit under effective goal weights
    eff_goal_w: dict[str, float] = {}
    goal_alignment_0_1 = 0.0
    g_mult = 1.0
    pair_goal_bonus = 0.0
    if user.recommendation_mode == "goals" and user.goal_vertical and user.goal_weights:
        eff_goal_w = effective_goal_weights(user)
        goal_match = _dot01(eff_goal_w, _goal_scores_for_product(product, user.goal_vertical))
        goal_alignment_0_1, _ = goal_alignment_01(product, user.goal_vertical, eff_goal_w)
        g_mult = goal_multiplier(goal_alignment_0_1, user.intent)
        pair_goal_bonus = goal_pair_synergy_bonus(product, user.goal_vertical, eff_goal_w)

    seasonal = 0.0
    if user.season != "unknown":
        seasonal = float(product.seasonal_scores.get(user.season, 0.0))

    lawn_context = is_lawnish(user) or (
        user.use_case is None
        and user.goal_vertical is None
        and float(user.problems.get("patchy_lawn", 0.0)) > 0
    )

    synergy = 0.0
    synergy += 0.4 if product.improves_soil_structure else 0.0
    synergy += 0.35 if product.improves_biology else 0.0
    synergy += 0.3 if product.improves_uptake else 0.0
    synergy += 0.2 if product.improves_fertiliser_efficiency else 0.0
    synergy += 0.2 if product.improves_water_infiltration else 0.0
    synergy += 0.15 if product.improves_visual_greening else 0.0

    targeted_bonus = 0.0
    yellowing = float(user.problems.get("yellowing", 0.0))
    patchy = float(user.problems.get("patchy_lawn", 0.0))
    slow = float(user.problems.get("slow_growth", 0.0))
    weak = float(user.problems.get("weak_roots", 0.0))
    lockout = float(user.problems.get("nutrient_lockout", 0.0))
    poor_flowering = float(user.problems.get("poor_flowering", 0.0))
    alkaline = float(user.soils.get("alkaline", 0.0))
    fungal = float(user.problems.get("fungal_issues", 0.0))
    if user.recommendation_mode == "problems":
        lawn_yellowing = yellowing >= 0.35 and lawn_context
        ironish = product.contains_iron or product.is_iron_based
        if lockout >= 0.35:
            if product.id == "414":
                targeted_bonus += 2.0
            elif product.id == "29814":
                targeted_bonus += 0.55
        if ironish and lawn_yellowing:
            targeted_bonus += 1.15 if alkaline >= 0.35 else 0.90
        elif yellowing >= 0.5 and ironish:
            targeted_bonus += 0.55
        if product.is_iron_chelate and alkaline >= 0.35 and yellowing >= 0.35:
            targeted_bonus += 0.25
        if yellowing >= 0.5 and slow >= 0.5 and product.role_type == RoleType.NUTRITION and ironish:
            targeted_bonus += 0.25
        if (
            lawn_context
            and product.role_type == RoleType.BUNDLE
            and yellowing >= 0.5
            and patchy >= 0.35
            and product.contains_iron
        ):
            targeted_bonus += 0.25
        if is_gardenish(user):
            if poor_flowering >= 0.35 and product.is_garden_reproductive:
                targeted_bonus += 1.05
            elif poor_flowering >= 0.35 and product.id in ("SWS", "1176"):
                targeted_bonus += 0.25
            if slow >= 0.35 and product.id in ("1156", "A8M"):
                targeted_bonus += 0.40
            if weak >= 0.35 and product.id == "1156":
                targeted_bonus += 0.90
            elif weak >= 0.35 and product.id == "SWS":
                targeted_bonus += 0.35
            if weak >= 0.35 and poor_flowering < 0.35 and product.is_garden_reproductive:
                targeted_bonus -= 0.45

    stage_alignment_bonus = 0.0
    stage_note: str | None = None
    if user.recommendation_mode == "goals":
        stage_alignment_bonus, stage_note = _garden_stage_alignment_bonus(product, user)

    context_fit = _context_fit(product, user)
    core_bonus = _core_range_bonus(product, user)

    if user.recommendation_mode == "goals":
        context_engine = (
            0.15 * weights.use_case * use_case_match
            + 0.12 * weights.seasonal * seasonal
            + 0.28 * weights.soil * soil_match
            + 0.05 * weights.synergy * synergy
            + 0.05 * weights.problem * problem_match
        )
        base = (
            weights.goal_segment * goal_match * g_mult
            + context_engine
            + pair_goal_bonus
            + stage_alignment_bonus
            + context_fit
            + core_bonus
        )
    else:
        base = (
            weights.problem * problem_match
            + weights.soil * soil_match
            + weights.use_case * use_case_match
            + weights.seasonal * seasonal
            + weights.synergy * synergy
            + targeted_bonus
            + context_fit
            + core_bonus
        )

    mult = role_multiplier(product.role_type, user=user)
    final = base * mult
    if product.is_high_nitrogen and user.season == "summer" and fungal >= 0.35:
        final *= 0.85
        # recorded below via reasons

    reasons: list[str] = []
    if user.recommendation_mode == "goals":
        reasons.append(
            f"Goal layer: align={goal_alignment_0_1:.2f} × mult={g_mult:.2f} (weighted priorities + intent)"
        )
        reasons.append(f"Goal CSV fit (effective weights): {goal_match:.2f}")
        if pair_goal_bonus > 0:
            reasons.append(f"Complementary goal synergy: +{pair_goal_bonus:.2f}")
        if soil_match > 0:
            reasons.append(f"Soil match: {soil_match:.2f}")
        if stage_alignment_bonus > 0 and stage_note:
            reasons.append(f"Stage alignment: +{stage_alignment_bonus:.2f} ({stage_note})")
    else:
        if problem_match > 0:
            reasons.append(f"Problem match: {problem_match:.2f}")
        if soil_match > 0:
            reasons.append(f"Soil match: {soil_match:.2f}")
    if use_case_match > 0:
        reasons.append(f"Use-case match: {use_case_match:.2f}")
    if seasonal > 0:
        reasons.append(f"Seasonal relevance: {seasonal:.2f}")
    if user.recommendation_mode == "problems" and targeted_bonus > 0:
        reasons.append(f"Targeted bonus: {targeted_bonus:.2f}")
    if core_bonus > 0:
        reasons.append("Core range (Lawn Lovers Starter / Pro)")
    if product.is_high_nitrogen and user.season == "summer" and fungal >= 0.35:
        reasons.append("High-N downweighted in summer with fungal pressure")
    reasons.append(f"Role priority: {product.role_type.value} × {mult:.2f}")

    return ScoredProduct(
        product=product,
        score=final,
        breakdown={
            "goal_scoring_active": 1.0 if user.recommendation_mode == "goals" else 0.0,
            "problem_match": problem_match,
            "soil_match": soil_match,
            "use_case_match": use_case_match,
            "goal_match": goal_match,
            "goal_alignment_01": goal_alignment_0_1,
            "goal_multiplier": g_mult,
            "pair_goal_synergy": pair_goal_bonus,
            "seasonal": seasonal,
            "synergy": synergy,
            "stage_alignment_bonus": stage_alignment_bonus,
            "targeted_bonus": targeted_bonus,
            "context_fit": context_fit,
            "core_range_bonus": core_bonus,
            "role_multiplier": mult,
            "base": base,
            "final": final,
        },
        reasons=reasons,
    )


def sort_scored(scored: list[ScoredProduct]) -> list[ScoredProduct]:
    return sorted(scored, key=lambda s: s.score, reverse=True)


def season_from_month(month: int) -> Season:
    # Southern hemisphere friendly by default (AU-focused).
    if month in (9, 10, 11):
        return "spring"
    if month in (12, 1, 2):
        return "summer"
    if month in (3, 4, 5):
        return "autumn"
    if month in (6, 7, 8):
        return "winter"
    return "unknown"


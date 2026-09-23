from __future__ import annotations

from pathlib import Path

from .bundles import top_bundles
from .catalog import Catalog
from .champion_turf import (
    CHAMPION_FAIRWAY_ID,
    CHAMPION_GREENS_ID,
    FAIRWAY_BLURB,
    FAIRWAY_LABEL,
    FAIRWAY_TAG,
    GREENS_BLURB,
    GREENS_LABEL,
    GREENS_TAG,
    champion_turf_pair_warranted,
)
from .constraints import is_lawnish, product_fits_context, recommended_max_stack
from .goal_layer import effective_goal_weights, majority_keep_it_healthy_goals
from .intent import build_user_input
from .scoring import Weights, score_product, sort_scored
from .stacking import build_stack, build_stack_goals, ensure_lawn_lovers_pro_pack
from .types import Product, Recommendation, RoleType, UserInput, ScoredProduct


_PROBLEM_LABELS = {
    "yellowing": "yellowing",
    "slow_growth": "slow growth",
    "weak_roots": "weak roots",
    "nutrient_lockout": "nutrient lockout",
    "patchy_lawn": "a patchy lawn",
    "compaction": "compaction",
    "poor_water_retention": "poor water holding",
    "fungal_issues": "fungal pressure",
    "poor_flowering": "poor flowering or fruiting",
}

_GOAL_LABELS = {
    "deep_green_colour": "deeper green colour",
    "thickening_and_density": "thicker, denser turf",
    "fast_recovery_from_stress": "faster recovery from stress",
    "weed_suppression_through_dominance": "a lawn that crowds out weeds",
    "low_maintenance_resilience": "low-maintenance resilience",
    "strong_flowering_and_fruiting": "more flowers, fruit and veg",
    "improved_soil_fertility": "richer soil over time",
    "root_development_transplant": "stronger roots and transplanting",
    "pest_and_disease_resilience": "pest and disease resilience",
    "consistent_growth_across_seasons": "steady growth through the year",
    "yield_increase": "higher yield",
    "soil_efficiency": "better soil efficiency",
    "water_efficiency": "better water efficiency",
    "crop_uniformity": "more even crops",
    "reduced_input_dependency": "less input dependence over time",
}

_USE_CASE_LABELS = {
    "lawn": "lawn",
    "garden_beds": "garden beds",
    "pots": "pots",
    "indoor_plants": "indoor plants",
    "farms": "farm / acreage",
}

_ROLE_JOB = {
    RoleType.BIOLOGY: "to support soil biology so plants use the rest of the program",
    RoleType.UPTAKE: "to help unlock and carry nutrients",
    RoleType.NUTRITION: "to feed growth",
    RoleType.VISUAL: "to restore colour where leaves or turf have yellowed",
    RoleType.SOIL_STRUCTURE: "to improve how the soil holds and moves water",
    RoleType.SOIL_CHEMISTRY: "to adjust soil pH so nutrients stay available",
    RoleType.BUNDLE: "as a one-pack option covering several steps",
}


def _join_en(items: list[str]) -> str:
    clean = [x for x in items if x]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return ", ".join(clean[:-1]) + f", and {clean[-1]}"


def _short_name(product: Product) -> str:
    name = (product.name or "").strip()
    if "(" in name:
        name = name.split("(")[0].strip()
    return name or "This product"


def _product_why(product: Product) -> str | None:
    reason = (getattr(product, "short_reason", None) or "").strip()
    if not reason:
        return None
    if reason.endswith("."):
        reason = reason[:-1]
    if len(reason) > 1:
        return reason[0].lower() + reason[1:]
    return reason.lower()


def _choice_summary(
    user: UserInput,
    stack: list[Product],
    *,
    fertiliser: Product | None,
    champion: dict | None,
    kits: list[Product],
    notes: list[str],
) -> list[str]:
    """Plain-language 'why these products' — no scores or engine jargon."""
    lines: list[str] = []

    place = _USE_CASE_LABELS.get(user.use_case or "", "")
    if user.recommendation_mode == "goals":
        wants = _join_en(
            [_GOAL_LABELS.get(k, k.replace("_", " ")) for k, v in user.goal_weights.items() if float(v) >= 0.35]
        )
        if place and wants:
            lines.append(f"This plan is for {place}, aiming for {wants}.")
        elif wants:
            lines.append(f"This plan is aiming for {wants}.")
        elif place:
            lines.append(f"This plan is for {place}.")
    else:
        issues = _join_en(
            [_PROBLEM_LABELS.get(k, k.replace("_", " ")) for k, v in user.problems.items() if float(v) >= 0.35]
        )
        if place and issues:
            lines.append(f"This plan is for {place}, to help with {issues}.")
        elif issues:
            lines.append(f"This plan is to help with {issues}.")
        elif place:
            lines.append(f"This plan is for {place}.")

    soils = _join_en([k.replace("_", " ") for k, v in user.soils.items() if float(v) >= 0.35])
    if soils:
        lines.append(f"Soil notes we used: {soils}.")
    for note in list(user.soil_test_notes)[:2]:
        if note:
            lines.append(str(note))

    seen: set[str] = set()
    for i, product in enumerate(stack):
        seen.add(product.id)
        why = _product_why(product)
        job = _ROLE_JOB.get(product.role_type)
        if i == 0:
            if why:
                lines.append(f"We start with {_short_name(product)} because {why}.")
            elif job:
                lines.append(f"We start with {_short_name(product)} {job}.")
            else:
                lines.append(f"We start with {_short_name(product)} as the best match for what you selected.")
        elif job:
            lines.append(f"Then {_short_name(product)} {job}.")
        elif why:
            lines.append(f"Then {_short_name(product)} because {why}.")
        else:
            lines.append(f"Then {_short_name(product)} to complete the program.")

    if fertiliser is not None and fertiliser.id not in seen:
        why = _product_why(fertiliser)
        if why:
            lines.append(f"The fertiliser pick is {_short_name(fertiliser)} because {why}.")
        else:
            lines.append(f"The fertiliser pick is {_short_name(fertiliser)} to feed growth.")

    if champion:
        lines.append(
            "Champion Fairway and Greens Grade are both shown so you can match mowing height — everyday lawns vs fine, low-cut turf."
        )

    for note in notes:
        if note:
            lines.append(str(note))

    if kits:
        lines.append("Kits are listed separately if you’d rather one pack than a few bottles.")

    return lines


def _champion_turf_pair(
    catalog: Catalog,
    user: UserInput,
    product_dict,
    scored_sorted: list[ScoredProduct],
    *,
    force: bool = False,
) -> dict[str, object] | None:
    """Surface both CHAMPION SKUs with tags only when scoring/goal weighting favours them vs the catalog."""
    if not force and not champion_turf_pair_warranted(user, scored_sorted):
        return None
    by_id = {p.id: p for p in catalog.products}
    fair = by_id.get(CHAMPION_FAIRWAY_ID)
    greens = by_id.get(CHAMPION_GREENS_ID)
    if fair is None or greens is None:
        return None
    return {
        "title": "CHAMPION professional turf fertilisers",
        "subtitle": "Both are valid turf nutrition options — choose by mowing height, maintenance intensity, and how precise the surface must be.",
        "fairway": {
            "tag": FAIRWAY_TAG,
            "label": FAIRWAY_LABEL,
            "description": FAIRWAY_BLURB,
            "product": product_dict(fair),
        },
        "greens_grade": {
            "tag": GREENS_TAG,
            "label": GREENS_LABEL,
            "description": GREENS_BLURB,
            "product": product_dict(greens),
        },
    }


def _goals_primary_fertiliser(scored_sorted: list[ScoredProduct], user: UserInput):
    """Highest-scored NUTRITION product for goals mode (explicit fertiliser line in UI)."""
    if user.recommendation_mode != "goals":
        return None
    # Planting stage: Roots, Shoots & Leaves is the vegetative feed.
    if (
        user.intent == "establishment_mode"
        and user.goal_vertical == "garden"
        and float(user.goal_weights.get("root_development_transplant", 0.0)) >= 0.35
    ):
        for sp in scored_sorted:
            if sp.product.id == "1156" and product_fits_context(sp.product, user).ok:
                return sp.product
    # Lawn Lovers core feed for turf goals (Activ8EXTRA), unless Champion pair is used.
    if is_lawnish(user):
        for sp in scored_sorted:
            if sp.product.id == "A8X" and product_fits_context(sp.product, user).ok:
                return sp.product
    for sp in scored_sorted:
        if sp.product.role_type != RoleType.NUTRITION:
            continue
        if sp.product.id == "575":
            continue
        if not product_fits_context(sp.product, user).ok:
            continue
        return sp.product
    return None


def recommend(
    raw_input: dict,
    *,
    catalog_csv_path: str | Path = Path(__file__).resolve().parents[1]
    / "data"
    / "plant_doctor_recommendation_engine_template.csv",
    max_stack: int | None = None,
    weights: Weights | None = None,
) -> Recommendation:
    """
    Main entry point.

    Input is a dict so you can feed it from UI, API, or an LLM parser.
    Output is a fully structured Recommendation object (deterministic).
    """
    user: UserInput = build_user_input(raw_input)
    w = weights or Weights()
    cap = recommended_max_stack(user) if max_stack is None else max_stack
    if majority_keep_it_healthy_goals(user) and is_lawnish(user):
        cap = max(cap, 7)

    catalog = Catalog.from_csv(catalog_csv_path)
    scored = [score_product(p, user, weights=w) for p in catalog.products]
    scored_sorted = sort_scored(scored)

    def product_dict(p) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "role_type": p.role_type.value,
            "image_url": getattr(p, "image_url", None),
            "product_url": getattr(p, "product_url", None),
            "short_reason": getattr(p, "short_reason", None),
            "problem_explanation": getattr(p, "problem_explanation", None),
            "why_this_works": getattr(p, "why_this_works", None),
        }

    upgrade = top_bundles(scored_sorted, user=user, limit=2)

    def input_snapshot() -> dict:
        snap = {
            "recommendation_mode": user.recommendation_mode,
            "goal_vertical": user.goal_vertical,
            "goal_weights": user.goal_weights,
            "use_case": user.use_case,
            "soils": user.soils,
            "soil_ph": user.soil_ph,
            "soil_ph_method": user.soil_ph_method if user.soil_ph is not None else None,
            "organic_matter_pct": user.organic_matter_pct,
            "soil_test_notes": list(user.soil_test_notes),
        }
        if user.recommendation_mode == "goals" and not user.goal_weights:
            snap["warning"] = "No goals selected — pick at least one goal, or results will be weak."
        elif user.recommendation_mode == "goals" and user.goal_vertical and user.goal_weights:
            egw = effective_goal_weights(user)
            if egw:
                snap["effective_goal_weights"] = egw
        return snap

    # Individual products are the plan. Kits stay in upgrade_path (“Or use a kit”).
    non_bundle_scored = [sp for sp in scored_sorted if sp.product.role_type != RoleType.BUNDLE]
    if user.recommendation_mode == "goals":
        plan = build_stack_goals(non_bundle_scored or scored_sorted, user, max_stack=cap)
        plan = ensure_lawn_lovers_pro_pack(plan, catalog.products, user)
    else:
        plan = build_stack(non_bundle_scored or scored_sorted, user, max_stack=cap)

    champ = _champion_turf_pair(
        catalog,
        user,
        product_dict,
        scored_sorted,
        force=majority_keep_it_healthy_goals(user) and is_lawnish(user),
    )
    fert_primary = _goals_primary_fertiliser(scored_sorted, user) if user.recommendation_mode == "goals" else None

    upgrade_path = upgrade

    explanations = {
        "bundle_override": False,
        "intent": user.intent,
        "confidence": user.confidence,
        "input": input_snapshot(),
        "champion_turf_pair": champ,
        "notes": plan.notes,
        "choice_summary": _choice_summary(
            user,
            plan.stack,
            fertiliser=fert_primary,
            champion=champ,
            kits=upgrade_path,
            notes=plan.notes,
        ),
        "top_candidates": [
            {
                "id": sp.product.id,
                "name": sp.product.name,
                "role_type": sp.product.role_type.value,
                "score": sp.score,
                "breakdown": sp.breakdown,
            }
            for sp in scored_sorted[:10]
        ],
    }

    return Recommendation(
        intent=user.intent,
        season=user.season,
        primary=plan.primary,
        stack=plan.stack,
        upgrade_path=upgrade_path,
        explanations=explanations,
        primary_fertiliser=fert_primary,
    )


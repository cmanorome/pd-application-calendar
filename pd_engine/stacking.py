from __future__ import annotations

from dataclasses import dataclass

from .constraints import (
    incompatible_with_stack,
    iron_humic_spacing_needed,
    is_gardenish,
    is_valid_primary,
    product_fits_context,
    recommended_max_stack,
    role_is_warranted,
)
from .types import Product, RoleType, ScoredProduct, UserInput


ROLE_ORDER: list[RoleType] = [
    RoleType.SOIL_STRUCTURE,
    RoleType.SOIL_CHEMISTRY,
    RoleType.BIOLOGY,
    RoleType.UPTAKE,
    RoleType.NUTRITION,
    RoleType.VISUAL,
]

# If a Lawn Lovers core SKU is close to the role leader, prefer it.
_CORE_PICK_RATIO = 0.85


@dataclass(frozen=True)
class StackPlan:
    primary: Product
    stack: list[Product]
    notes: list[str]


def _preferred_core(product: Product, user: UserInput) -> bool:
    if not product.is_core_range:
        return False
    if is_gardenish(user) and product.id == "A8X":
        return False
    return True


def _first_eligible(scored: list[ScoredProduct], role: RoleType, stack: list[Product], user: UserInput) -> list[ScoredProduct]:
    iron_in_stack = any(p.is_iron_based for p in stack)
    out: list[ScoredProduct] = []
    for sp in scored:
        if sp.product.role_type != role:
            continue
        if any(p.id == sp.product.id for p in stack):
            continue
        # Prefer seaweed over neem as the default biology layer unless disease/pest is in play.
        if role == RoleType.BIOLOGY and sp.product.id == "758":
            fungal = float(user.problems.get("fungal_issues", 0.0)) >= 0.35
            pest_goal = float(user.goal_weights.get("pest_and_disease_resilience", 0.0)) >= 0.35
            if not fungal and not pest_goal:
                continue
        res = incompatible_with_stack(sp.product, stack, user)
        if not res.ok:
            continue
        if sp.product.is_iron_based and any(p.is_iron_based for p in stack):
            continue
        out.append(sp)
    if out:
        return out
    # Second pass: if uptake was skipped for tank-mix, still allow a humic later in the program.
    if iron_in_stack and role == RoleType.UPTAKE:
        for sp in scored:
            if sp.product.role_type != role:
                continue
            if any(p.id == sp.product.id for p in stack):
                continue
            if incompatible_with_stack(sp.product, stack, user).ok:
                out.append(sp)
    return out


def _pick_from_role(scored: list[ScoredProduct], role: RoleType, stack: list[Product], user: UserInput) -> Product | None:
    candidates = _first_eligible(scored, role, stack, user)
    if not candidates:
        return None
    core = next((sp for sp in candidates if _preferred_core(sp.product, user)), None)
    if core is not None:
        return core.product
    return candidates[0].product


def _finish_plan(stack: list[Product], notes: list[str]) -> StackPlan:
    if iron_humic_spacing_needed(stack):
        notes.append(
            "Apply liquid iron on a different day from seaweed, humic, or soil wetter — do not mix them in the same sprayer."
        )
    primary = stack[0]
    rest = stack[1:]
    role_rank = {r: i for i, r in enumerate(ROLE_ORDER)}
    rest_sorted = sorted(rest, key=lambda p: role_rank.get(p.role_type, 999))
    return StackPlan(primary=primary, stack=[primary] + rest_sorted, notes=notes)


def _pick_primary_from(scored: list[ScoredProduct], user: UserInput, *, skip_nutrition: bool = False) -> Product | None:
    first: ScoredProduct | None = None
    core: ScoredProduct | None = None
    for sp in scored:
        if skip_nutrition and sp.product.role_type == RoleType.NUTRITION:
            continue
        if not is_valid_primary(sp.product, user).ok:
            continue
        if first is None:
            first = sp
        if core is None and _preferred_core(sp.product, user):
            core = sp
        if first is not None and core is not None:
            break
    if first is None:
        return None
    if core is not None and core.score >= first.score * _CORE_PICK_RATIO:
        return core.product
    return first.product


def build_stack(scored: list[ScoredProduct], user: UserInput, *, max_stack: int | None = None) -> StackPlan:
    """
    Problems mode stacking:
    - best valid primary
    - extra layers only when the user's symptoms/soils warrant that role
    """
    notes: list[str] = []
    cap = max_stack if max_stack is not None else recommended_max_stack(user)

    primary = _pick_primary_from(scored, user)
    if primary is None:
        for sp in scored:
            if sp.product.role_type != RoleType.VISUAL and product_fits_context(sp.product, user).ok:
                primary = sp.product
                notes.append("Fallback primary selection applied.")
                break
    if primary is None:
        for sp in scored:
            if sp.product.role_type != RoleType.VISUAL:
                primary = sp.product
                notes.append("Fallback primary selection applied.")
                break
    if primary is None:
        raise RuntimeError("No valid primary product found.")

    stack: list[Product] = [primary]

    for role in ROLE_ORDER:
        if len(stack) >= cap:
            break
        if role == primary.role_type:
            continue
        if (
            user.recommendation_mode == "problems"
            and role == RoleType.NUTRITION
            and primary.role_type != RoleType.NUTRITION
            and not role_is_warranted(role, user)
        ):
            continue
        if not role_is_warranted(role, user) and role != RoleType.NUTRITION:
            continue
        picked = _pick_from_role(scored, role, stack, user)
        if picked is not None:
            stack.append(picked)

    return _finish_plan(stack, notes)


def _garden_feed_should_lead(user: UserInput) -> bool:
    if user.recommendation_mode != "goals" or user.goal_vertical != "garden":
        return False
    gw = user.goal_weights
    flower = float(gw.get("strong_flowering_and_fruiting", 0.0))
    roots = float(gw.get("root_development_transplant", 0.0))
    fertility = float(gw.get("improved_soil_fertility", 0.0))
    if flower >= 0.35 and fertility < 0.35:
        return True
    if user.intent == "establishment_mode" and roots >= 0.35 and flower < 0.35:
        return True
    return False


def _pick_goals_foundation_primary(scored: list[ScoredProduct], user: UserInput) -> tuple[Product, list[str]]:
    notes: list[str] = []
    if _garden_feed_should_lead(user):
        for sp in scored:
            if sp.product.role_type != RoleType.NUTRITION:
                continue
            if is_valid_primary(sp.product, user).ok:
                return sp.product, notes
    primary = _pick_primary_from(scored, user, skip_nutrition=True)
    if primary is not None:
        return primary, notes
    primary = _pick_primary_from(scored, user)
    if primary is not None:
        return primary, notes
    for sp in scored:
        if sp.product.role_type != RoleType.VISUAL:
            notes.append("Fallback primary selection applied.")
            return sp.product, notes
    raise RuntimeError("No valid primary product found.")


def build_stack_goals(scored: list[ScoredProduct], user: UserInput, *, max_stack: int | None = None) -> StackPlan:
    cap = max_stack if max_stack is not None else recommended_max_stack(user)
    primary, notes = _pick_goals_foundation_primary(scored, user)
    stack: list[Product] = [primary]

    for role in ROLE_ORDER:
        if role == RoleType.NUTRITION:
            continue
        if len(stack) >= cap:
            break
        if role == primary.role_type:
            continue
        if not role_is_warranted(role, user):
            continue
        picked = _pick_from_role(scored, role, stack, user)
        if picked is not None:
            stack.append(picked)

    return _finish_plan(stack, notes)


def ensure_goals_fertiliser(
    plan: StackPlan,
    scored: list[ScoredProduct],
    user: UserInput,
    *,
    max_stack: int,
) -> StackPlan:
    if user.recommendation_mode != "goals":
        return plan
    if any(p.role_type == RoleType.NUTRITION for p in plan.stack):
        return plan

    in_stack = {p.id for p in plan.stack}
    chosen: Product | None = None
    for sp in scored:
        if sp.product.role_type != RoleType.NUTRITION:
            continue
        if sp.product.id in in_stack:
            continue
        if incompatible_with_stack(sp.product, plan.stack, user).ok:
            chosen = sp.product
            break

    notes = list(plan.notes)
    if chosen is None:
        notes.append("Goals mode: no compatible fertiliser could be added (constraints).")
        return StackPlan(primary=plan.primary, stack=plan.stack, notes=notes)

    stack = list(plan.stack)
    if len(stack) >= max_stack:
        vis_idx = next((i for i, p in enumerate(stack) if i > 0 and p.role_type == RoleType.VISUAL), None)
        if vis_idx is not None:
            stack.pop(vis_idx)
        else:
            stack.pop()

    stack.append(chosen)
    notes.append("Goals mode: added a recommended fertiliser so the plan always includes nutrition.")
    return _finish_plan(stack, notes)

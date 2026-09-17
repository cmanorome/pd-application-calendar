from __future__ import annotations

from dataclasses import dataclass

from .constraints import product_fits_context
from .types import Product, RoleType, ScoredProduct, UserInput

def _bundle_matches_goals_vertical(product: Product, user: UserInput) -> bool:
    """
    In goals mode, drop bundles whose CSV goal-column totals skew to another vertical
    (e.g. no garden-heavy bundles when lawn goals are selected).
    """
    if user.recommendation_mode != "goals" or not user.goal_vertical:
        return True
    if product.role_type != RoleType.BUNDLE:
        return True
    lawn_tot = sum(float(v) for v in product.lawn_goal_scores.values())
    garden_tot = sum(float(v) for v in product.garden_goal_scores.values())
    farm_tot = sum(float(v) for v in product.farm_goal_scores.values())
    gv = user.goal_vertical
    if gv == "lawn":
        return garden_tot <= lawn_tot
    if gv == "garden":
        return lawn_tot <= garden_tot
    if gv == "farm":
        return max(lawn_tot, garden_tot) <= farm_tot
    return True


@dataclass(frozen=True)
class BundleDecision:
    should_override: bool
    reason: str | None


def bundle_override_decision(user: UserInput) -> BundleDecision:
    """Kits stay in the upgrade path — never replace the step-by-step product plan."""
    return BundleDecision(False, None)


def top_bundles(
    scored: list[ScoredProduct],
    *,
    user: UserInput | None = None,
    limit: int = 3,
) -> list[Product]:
    bundles = [
        sp
        for sp in scored
        if sp.product.role_type == RoleType.BUNDLE
        and (user is None or _bundle_matches_goals_vertical(sp.product, user))
        and (user is None or product_fits_context(sp.product, user).ok)
    ]
    bundles_sorted = sorted(bundles, key=lambda s: s.score, reverse=True)
    return [b.product for b in bundles_sorted[:limit]]


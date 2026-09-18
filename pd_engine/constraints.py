from __future__ import annotations

from dataclasses import dataclass

from .soil_test import lime_is_appropriate
from .types import Product, RoleType, UserInput


@dataclass(frozen=True)
class ConstraintResult:
    ok: bool
    reason: str | None = None


def iron_humic_spacing_needed(stack: list[Product]) -> bool:
    """Liquid iron and humic/seaweed/wetter can share a program, but not a tank."""
    return any(p.is_iron_based for p in stack) and any(p.is_incompatible_with_iron for p in stack)


def _on(user: UserInput, group: dict, key: str, thresh: float = 0.35) -> bool:
    return float(group.get(key, 0.0)) >= thresh


def is_lawnish(user: UserInput) -> bool:
    return user.use_case == "lawn" or user.goal_vertical == "lawn"


def is_gardenish(user: UserInput) -> bool:
    return user.use_case in ("garden_beds", "pots", "indoor_plants") or user.goal_vertical == "garden"


def is_farmish(user: UserInput) -> bool:
    return user.use_case == "farms" or user.goal_vertical == "farm"


def product_fits_context(product: Product, user: UserInput) -> ConstraintResult:
    """Soft agronomic fit — skip products that don't match the selected situation."""
    lawnish = is_lawnish(user)
    farmish = is_farmish(user)
    gardenish = is_gardenish(user)
    flowering_intent = (
        float(user.goal_weights.get("strong_flowering_and_fruiting", 0.0)) >= 0.35
        or _on(user, user.problems, "poor_flowering")
    )

    if product.is_garden_reproductive and lawnish:
        return ConstraintResult(False, "Flower/fruit fertiliser is not a lawn feed.")
    if product.is_garden_reproductive and user.use_case in ("indoor_plants", "pots"):
        if not flowering_intent:
            return ConstraintResult(False, "Flower/fruit fertiliser is not the default indoor/pot feed.")
    if user.use_case in ("indoor_plants", "pots") and product.id in ("1156", "886", "892", "575"):
        return ConstraintResult(False, "Granular turf/garden-bed fertiliser is a poor fit for pots or indoor plants.")
    if product.is_lawn_specialist and user.use_case in ("indoor_plants", "pots"):
        return ConstraintResult(False, "Lawn-specialist product is a poor fit for indoor plants or pots.")
    if product.is_lawn_specialist and farmish and product.role_type in (
        RoleType.NUTRITION,
        RoleType.VISUAL,
        RoleType.BUNDLE,
    ):
        return ConstraintResult(False, "Lawn-specialist product is a poor fit for farm/crop programs.")
    if product.is_lawn_specialist and gardenish:
        return ConstraintResult(False, "Turf fertiliser is a poor fit for garden beds.")

    if product.is_lime_based:
        if _on(user, user.soils, "alkaline"):
            return ConstraintResult(False, "Do not apply lime/dolomite on alkaline soil.")
        if not lime_is_appropriate(user.soil_ph, user.soil_ph_method):
            return ConstraintResult(False, "Measured pH is not acidic — skip lime/dolomite.")
        if user.soil_ph is None and not _on(user, user.soils, "acidic"):
            return ConstraintResult(False, "Lime only when soil is acidic (or a pH test shows it).")

    if product.is_gypsum:
        if not (
            _on(user, user.soils, "clay")
            or _on(user, user.problems, "compaction")
        ):
            return ConstraintResult(False, "Gypsum is for clay, sodic, or compacted soils.")

    if product.is_wetter:
        if not (
            _on(user, user.soils, "hydrophobic")
            or _on(user, user.problems, "poor_water_retention")
        ):
            return ConstraintResult(False, "Soil wetter is for water-repellent or poorly wetting soil.")

    if product.id == "557":  # zeolite — sandy / leachy / low OM, not a default lockout fix
        if not (
            _on(user, user.soils, "sandy")
            or _on(user, user.soils, "low_organic_matter")
        ):
            return ConstraintResult(False, "Zeolite is for sandy, leachy, or low-buffer soils.")

    if product.role_type == RoleType.VISUAL and product.is_iron_sulphate:
        if _on(user, user.soils, "alkaline") and user.soil_ph is not None:
            # Prefer chelate on high pH; still allow sulphate if nothing else fits
            pass

    return ConstraintResult(True)


def incompatible_with_stack(candidate: Product, stack: list[Product], user: UserInput) -> ConstraintResult:
    fit = product_fits_context(candidate, user)
    if not fit.ok:
        return fit

    if candidate.is_iron_based and any(p.is_iron_based for p in stack):
        return ConstraintResult(ok=False, reason="Avoid stacking multiple iron-based products.")

    if candidate.is_lime_based and any(p.is_iron_sulphate for p in stack):
        return ConstraintResult(ok=False, reason="Do not combine lime/dolomite with iron sulphate.")
    if candidate.is_iron_sulphate and any(p.is_lime_based for p in stack):
        return ConstraintResult(ok=False, reason="Do not combine iron sulphate with lime/dolomite.")
    if (candidate.is_iron_based or candidate.contains_iron) and any(p.is_lime_based for p in stack):
        return ConstraintResult(ok=False, reason="Apply lime first; add iron in a later application after pH adjusts.")
    if candidate.is_lime_based and any(p.is_iron_based or p.contains_iron for p in stack):
        return ConstraintResult(ok=False, reason="Do not combine lime with iron products.")

    lockout = float(user.problems.get("nutrient_lockout", 0.0))
    if lockout >= 0.5 and candidate.role_type == RoleType.NUTRITION:
        has_unlock_layer = any(
            p.role_type in (RoleType.UPTAKE, RoleType.BIOLOGY, RoleType.SOIL_CHEMISTRY) for p in stack
        )
        if not has_unlock_layer:
            return ConstraintResult(
                ok=False,
                reason="Nutrient lockout present: address biology/uptake/chemistry before fertiliser.",
            )

    yellowing = float(user.problems.get("yellowing", 0.0))
    if candidate.role_type == RoleType.VISUAL:
        chlorosis_lead = yellowing >= 0.5 and lockout < 0.5
        has_foundation = any(
            p.role_type
            in (RoleType.SOIL_STRUCTURE, RoleType.SOIL_CHEMISTRY, RoleType.BIOLOGY, RoleType.UPTAKE)
            for p in stack
        )
        if not chlorosis_lead and not has_foundation:
            return ConstraintResult(
                ok=False,
                reason="Visual products must come after soil/biology/uptake foundations.",
            )

    return ConstraintResult(ok=True)


def is_valid_primary(primary: Product, user: UserInput) -> ConstraintResult:
    fit = product_fits_context(primary, user)
    if not fit.ok:
        return fit

    lockout = float(user.problems.get("nutrient_lockout", 0.0))
    yellowing = float(user.problems.get("yellowing", 0.0))
    if primary.role_type == RoleType.VISUAL:
        if yellowing >= 0.5 and lockout < 0.5:
            return ConstraintResult(ok=True)
        return ConstraintResult(ok=False, reason="Visual products cannot be primary unless yellowing is the main issue.")
    if lockout >= 0.5 and primary.role_type == RoleType.NUTRITION:
        return ConstraintResult(
            ok=False,
            reason="Nutrient lockout present: do not lead with fertiliser without unlock layers.",
        )
    return ConstraintResult(ok=True)


def role_is_warranted(role: RoleType, user: UserInput) -> bool:
    """Only add a stack layer when the user's situation calls for it."""
    if role == RoleType.SOIL_STRUCTURE:
        return (
            _on(user, user.soils, "clay")
            or _on(user, user.soils, "sandy")
            or _on(user, user.soils, "hydrophobic")
            or _on(user, user.problems, "compaction")
            or _on(user, user.problems, "poor_water_retention")
        )
    if role == RoleType.SOIL_CHEMISTRY:
        return (
            _on(user, user.soils, "acidic")
            or _on(user, user.soils, "alkaline")
            or _on(user, user.problems, "nutrient_lockout")
        )
    if role == RoleType.BIOLOGY:
        # Seaweed is Plant Doctor's default support layer, not only a rescue input.
        return True
    if role == RoleType.UPTAKE:
        return True
    if role == RoleType.NUTRITION:
        if user.recommendation_mode == "goals":
            return False  # surfaced separately
        return (
            _on(user, user.problems, "slow_growth")
            or _on(user, user.problems, "patchy_lawn")
            or _on(user, user.problems, "weak_roots")
            or _on(user, user.problems, "fungal_issues")
            or _on(user, user.problems, "poor_flowering")
        )
    if role == RoleType.VISUAL:
        if _on(user, user.problems, "yellowing"):
            return True
        return (
            user.recommendation_mode == "goals"
            and is_lawnish(user)
            and float(user.goal_weights.get("deep_green_colour", 0.0)) >= 0.35
        )
    return True


def recommended_max_stack(user: UserInput, default: int = 4) -> int:
    lockout = _on(user, user.problems, "nutrient_lockout", 0.5)
    structure = (
        _on(user, user.soils, "clay")
        or _on(user, user.problems, "compaction")
        or _on(user, user.soils, "hydrophobic")
    )
    return 5 if lockout and structure else default

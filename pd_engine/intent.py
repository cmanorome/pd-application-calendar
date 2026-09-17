from __future__ import annotations

from .goal_columns import ALL_GOAL_KEYS
from .soil_test import merge_soil_test, parse_soil_test_fields
from .types import GoalVertical, Intent, RecommendationMode, UserInput


def classify_intent(raw: dict) -> Intent:
    """
    Lightweight intent classifier (used for goals mode; see build_user_input for problems).

    If not provided, applies deterministic heuristics (v1).
    """
    v = (raw.get("intent") or "").strip().lower()
    if v:
        mapped = {
            "rescue": "rescue_mode",
            "rescue_mode": "rescue_mode",
            "maintenance": "maintenance_mode",
            "maintenance_mode": "maintenance_mode",
            "performance": "performance_mode",
            "performance_mode": "performance_mode",
            "establishment": "establishment_mode",
            "establishment_mode": "establishment_mode",
            "diagnosis": "diagnosis_mode",
            "diagnosis_mode": "diagnosis_mode",
            # Legacy: budget intent removed — treat as maintenance.
            "budget": "maintenance_mode",
            "budget_mode": "maintenance_mode",
        }.get(v)
        if mapped:
            return mapped  # type: ignore[return-value]

    # Heuristics from signals
    urgency = float(raw.get("urgency", 0) or 0)
    budget_sensitive = bool(raw.get("budget_sensitive", False))
    new_turf = bool(raw.get("new_turf", False))
    wants_fast_visual = bool(raw.get("wants_fast_visual", False))
    wants_diagnosis = bool(raw.get("wants_diagnosis", False))

    if wants_diagnosis:
        return "diagnosis_mode"
    if new_turf:
        return "establishment_mode"
    if budget_sensitive:
        return "maintenance_mode"
    if urgency >= 0.7 or wants_fast_visual:
        return "rescue_mode"
    if urgency >= 0.4:
        return "performance_mode"
    return "maintenance_mode"


def build_user_input(raw: dict) -> UserInput:
    intent = classify_intent(raw)
    season = (raw.get("season") or "unknown").strip().lower()
    if season not in {"spring", "summer", "autumn", "winter"}:
        season = "unknown"

    use_case = (raw.get("use_case") or "").strip().lower()
    if use_case not in {"lawn", "garden_beds", "indoor_plants", "pots", "farms"}:
        use_case = ""

    mode = (raw.get("recommendation_mode") or "problems").strip().lower()
    if mode not in ("problems", "goals"):
        mode = "problems"
    recommendation_mode: RecommendationMode = mode  # type: ignore[assignment]

    # Symptom-oriented intents are not used in goals mode (UI/API align on maintenance as fallback).
    if recommendation_mode == "goals" and intent in ("diagnosis_mode", "rescue_mode"):
        intent = "maintenance_mode"

    # Problems mode is always “fix what’s wrong” — same weighting as rescue (no separate intent).
    if recommendation_mode == "problems":
        intent = "rescue_mode"

    gv = (raw.get("goal_vertical") or "").strip().lower()
    if gv not in ("lawn", "garden", "farm"):
        gv = ""
    goal_vertical: GoalVertical | None = gv or None  # type: ignore[assignment]

    # goal_weights: { internal_key: float }
    gw = raw.get("goal_weights") or {}
    goal_weights: dict[str, float] = {}
    if isinstance(gw, dict):
        for k, v in gw.items():
            ks = str(k).strip()
            if ks in ALL_GOAL_KEYS:
                try:
                    fv = float(v)
                    if fv > 0:
                        goal_weights[ks] = max(0.0, min(1.0, fv))
                except (TypeError, ValueError):
                    pass

    # If goals mode but no vertical, infer from use_case
    if recommendation_mode == "goals" and goal_vertical is None and use_case:
        if use_case == "lawn":
            goal_vertical = "lawn"
        elif use_case == "farms":
            goal_vertical = "farm"
        elif use_case in ("garden_beds", "indoor_plants", "pots"):
            goal_vertical = "garden"

    # If goals mode has a vertical but no use_case, map for compatibility scoring
    if recommendation_mode == "goals" and goal_vertical and not use_case:
        if goal_vertical == "lawn":
            use_case = "lawn"
        elif goal_vertical == "garden":
            use_case = "garden_beds"
        elif goal_vertical == "farm":
            use_case = "farms"

    problems = raw.get("problems") or {}
    soils_raw = raw.get("soils") or {}
    soils = {k: float(v) for k, v in soils_raw.items() if float(v) > 0}
    confidence = float(raw.get("confidence", 0.6) or 0.6)
    confidence = max(0.0, min(1.0, confidence))

    soil_ph, ph_method, om_pct = parse_soil_test_fields(raw)
    soils, soil_notes = merge_soil_test(
        soils,
        ph=soil_ph,
        method=ph_method,
        organic_matter_pct=om_pct,
    )
    if soil_ph is not None or om_pct is not None:
        confidence = min(1.0, confidence + 0.08)

    return UserInput(
        intent=intent,
        season=season,  # type: ignore[arg-type]
        use_case=(use_case or None),  # type: ignore[arg-type]
        recommendation_mode=recommendation_mode,
        goal_vertical=goal_vertical,
        goal_weights=goal_weights,
        problems={k: float(v) for k, v in problems.items()},
        soils=soils,
        confidence=confidence,
        soil_ph=soil_ph,
        soil_ph_method=ph_method,
        organic_matter_pct=om_pct,
        soil_test_notes=soil_notes,
    )


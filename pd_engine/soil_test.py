"""Interpret optional soil-test numbers into engine soil tags.

Australian labs often report pH in CaCl2 (typically 0.5–0.8 lower than water).
Home kits are usually pH (water). Measured values override checkbox guesses.
"""

from __future__ import annotations

from typing import Any

from .types import PhMethod, SoilKey


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_soil_test_fields(raw: dict) -> tuple[float | None, PhMethod, float | None]:
    nested = raw.get("soil_test") if isinstance(raw.get("soil_test"), dict) else {}
    ph = _to_float(raw.get("soil_ph", nested.get("ph") if nested else None))
    om = _to_float(
        raw.get("organic_matter_pct", nested.get("organic_matter_pct") if nested else None)
    )
    method_raw = str(
        raw.get("soil_ph_method", nested.get("ph_method") if nested else "water") or "water"
    ).strip().lower()
    method: PhMethod = "cacl2" if method_raw in ("cacl2", "cacl₂", "cacl2", "calcium chloride") else "water"

    if ph is not None:
        if ph < 3.0 or ph > 11.0:
            ph = None
        else:
            ph = round(ph, 2)
    if om is not None:
        if om < 0 or om > 40:
            om = None
        else:
            om = round(om, 2)
    return ph, method, om


def interpret_ph(ph: float, method: PhMethod) -> tuple[float, float, str]:
    """Return (acidic_0_1, alkaline_0_1, short label)."""
    # CaCl2 is more acidic-looking than water pH; use slightly lower thresholds.
    if method == "cacl2":
        if ph < 4.8:
            return 1.0, 0.0, "strongly acidic"
        if ph < 5.3:
            return 0.7, 0.0, "acidic"
        if ph <= 6.5:
            return 0.0, 0.0, "near-neutral"
        if ph <= 7.0:
            return 0.0, 0.55, "slightly alkaline"
        return 0.0, 1.0, "alkaline"

    if ph < 5.5:
        return 1.0, 0.0, "acidic"
    if ph < 6.0:
        return 0.55, 0.0, "slightly acidic"
    if ph <= 7.2:
        return 0.0, 0.0, "near-neutral"
    if ph <= 7.6:
        return 0.0, 0.55, "slightly alkaline"
    return 0.0, 1.0, "alkaline"


def lime_is_appropriate(ph: float | None, method: PhMethod) -> bool:
    """Lime/dolomite only when the soil is actually acidic."""
    if ph is None:
        return True  # no measurement — rely on acidic checkbox + other constraints
    acidic, alkaline, _ = interpret_ph(ph, method)
    return acidic >= 0.5 and alkaline < 0.35


def merge_soil_test(
    soils: dict[str, float],
    *,
    ph: float | None,
    method: PhMethod,
    organic_matter_pct: float | None,
) -> tuple[dict[SoilKey, float], tuple[str, ...]]:
    """Overlay measured pH / OM onto checkbox soil tags. Measurement wins for pH and OM."""
    out: dict[str, float] = dict(soils)
    notes: list[str] = []

    if ph is not None:
        acidic, alkaline, label = interpret_ph(ph, method)
        method_label = "CaCl₂" if method == "cacl2" else "water"
        notes.append(f"Measured pH {ph:.1f} ({method_label}) — {label}.")
        # Clear checkbox pH tags so a wrong tick cannot fight the lab number.
        out.pop("acidic", None)
        out.pop("alkaline", None)
        if acidic > 0:
            out["acidic"] = acidic
            notes.append("Lime/dolomite may help nutrient availability.")
        if alkaline > 0:
            out["alkaline"] = alkaline
            notes.append("Skip lime. Iron and some trace elements are more likely to lock out.")
        if acidic <= 0 and alkaline <= 0:
            notes.append("pH is in a workable range — no lime or acidifying amendment from pH alone.")

    if organic_matter_pct is not None:
        notes.append(f"Organic matter {organic_matter_pct:.1f}%.")
        if organic_matter_pct < 2.0:
            out["low_organic_matter"] = 1.0
            notes.append("Low organic matter — biology and carbon (humic/compost/seaweed) are useful.")
        elif organic_matter_pct < 3.0:
            out["low_organic_matter"] = 0.45
        else:
            out.pop("low_organic_matter", None)

    cleaned = {k: float(v) for k, v in out.items() if float(v) > 0}
    return cleaned, tuple(notes)  # type: ignore[return-value]

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .goal_columns import FARM_GOAL_COLS, GARDEN_GOAL_COLS, LAWN_GOAL_COLS
from .types import Product, RoleType, Season


_PROBLEM_COLS = {
    "yellowing": "Yellowing Leaves",
    "slow_growth": "Slow Growth",
    "compaction": "Compacted Soil",
    "poor_water_retention": "Poor Water Retention",
    "nutrient_lockout": "Nutrient Lockout",
    "patchy_lawn": "Patchy Lawn",
    "fungal_issues": "Fungal Issues",
    "weak_roots": "Weak Roots",
}

_SOIL_COLS = {
    "sandy": "Sandy Soil",
    "clay": "Clay Soil",
    "acidic": "Acidic Soil",
    "alkaline": "Alkaline Soil",
    "low_organic_matter": "Low Organic Matter",
    "hydrophobic": "Hydrophobic Soil",
}

_SEASON_COLS: dict[Season, str] = {
    "spring": "Spring",
    "summer": "Summer",
    "autumn": "Autumn",
    "winter": "Winter",
}

_USE_CASE_COLS = {
    "lawn": "Lawn",
    "garden_beds": "Garden Beds",
    "indoor_plants": "Indoor Plants",
    "pots": "Pots",
    "farms": "Farms",
}


def _to_float(v: str | None, default: float = 0.0) -> float:
    if v is None:
        return default
    s = str(v).strip()
    if s == "":
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


# Known catalog SKUs — keyword fallback is for future rows only.
_SKU_ROLE: dict[str, RoleType] = {
    "A8X": RoleType.NUTRITION,
    "A8M": RoleType.NUTRITION,
    "886": RoleType.NUTRITION,
    "892": RoleType.NUTRITION,
    "575": RoleType.NUTRITION,
    "721": RoleType.NUTRITION,
    "LEN": RoleType.NUTRITION,
    "LIR": RoleType.VISUAL,
    "MG": RoleType.NUTRITION,
    "758": RoleType.BIOLOGY,
    "1156": RoleType.NUTRITION,
    "414": RoleType.UPTAKE,
    "1075": RoleType.SOIL_STRUCTURE,
    "513": RoleType.UPTAKE,
    "LIMEGr": RoleType.SOIL_CHEMISTRY,
    "664": RoleType.SOIL_STRUCTURE,
    "NSWL": RoleType.SOIL_STRUCTURE,
    "526": RoleType.UPTAKE,
    "29800": RoleType.UPTAKE,
    "29782": RoleType.BIOLOGY,
    "SWS": RoleType.BIOLOGY,
    "STM": RoleType.UPTAKE,
    "557": RoleType.SOIL_STRUCTURE,
    "DOL": RoleType.SOIL_CHEMISTRY,
    "846": RoleType.VISUAL,
    "547": RoleType.VISUAL,
    "636": RoleType.SOIL_STRUCTURE,
    "29814": RoleType.UPTAKE,
    "WMP": RoleType.BIOLOGY,
    "WMB": RoleType.BIOLOGY,
    "1318": RoleType.BUNDLE,
    "1176": RoleType.BUNDLE,
    "1243": RoleType.BUNDLE,
    "1231": RoleType.BUNDLE,
    "1235": RoleType.BUNDLE,
    "1247": RoleType.BUNDLE,
    "1239": RoleType.BUNDLE,
    "1253": RoleType.BUNDLE,
}

_LIQUID_IRON_SKUS = frozenset({"LIR", "MG", "846", "547"})
_CONTAINS_IRON_SKUS = _LIQUID_IRON_SKUS | {"886", "892", "LEN", "1231", "1253"}
_CHELATE_SKUS = frozenset({"547"})
_HIGH_N_SKUS = frozenset({"MG", "A8X"})
# Labels: do not tank-mix with iron. Stimulizer is explicitly mixable with iron.
_IRON_INCOMPATIBLE_SKUS = frozenset(
    {"SWS", "29782", "29800", "414", "513", "526", "29814", "NSWL", "664", "A8X", "A8M", "WMB"}
)
_GYPSUM_SKUS = frozenset({"1075", "636"})
_WETTER_SKUS = frozenset({"664", "NSWL"})
_LAWN_SPECIALIST_SKUS = frozenset({"886", "892", "LEN", "MG", "1231", "1235", "1239", "1253", "1243"})
_GARDEN_REPRODUCTIVE_SKUS = frozenset({"575", "721"})
# Lawn Lovers Starter (SWS + A8X + NSWL) and Pro (adds Quantum H, Liquid Iron, Stimulizer)
_CORE_RANGE_SKUS = frozenset({"SWS", "A8X", "NSWL", "29800", "LIR", "STM"})


def _has_token(blob: str, *tokens: str) -> bool:
    for t in tokens:
        if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", blob):
            return True
    return False


def _infer_role_type(
    sku: str,
    category: str,
    role_raw: str,
    primary_function: str,
    name: str,
) -> RoleType:
    if sku in _SKU_ROLE:
        return _SKU_ROLE[sku]

    blob = _norm(" ".join([category, role_raw, primary_function, name]))

    if any(k in blob for k in ["bundle", "pack", "starter kit", "pro pack", "system bundle"]):
        return RoleType.BUNDLE
    if any(k in blob for k in ["gypsum", "clay buster", "soil wetter", "wetting agent", "hydrophobic"]):
        return RoleType.SOIL_STRUCTURE
    if any(k in blob for k in ["lime", "dolomite", "calcium carbonate", "magnesium carbonate"]) or _has_token(
        blob, "ph"
    ):
        return RoleType.SOIL_CHEMISTRY
    if any(k in blob for k in ["seaweed", "kelp", "ascophyllum", "worm casting", "vermicast", "compost tea"]):
        return RoleType.BIOLOGY
    if any(k in blob for k in ["fulvic", "humic", "humate", "stimulizer"]):
        return RoleType.UPTAKE
    if any(k in blob for k in ["iron sulphate", "ferrous", "iron chelate", "liquid iron", "chlorosis"]):
        return RoleType.VISUAL
    if any(k in blob for k in ["fertiliser", "fertilizer", "npk", "slow-release", "controlled-release"]):
        return RoleType.NUTRITION
    if _has_token(blob, "inoculant") or "biostimulant" in blob:
        return RoleType.BIOLOGY
    if "zeolite" in blob or "clinoptilolite" in blob:
        return RoleType.SOIL_STRUCTURE
    return RoleType.NUTRITION


def _extract_visual_assets(visual_code_html: str) -> tuple[str | None, str | None]:
    """
    The template CSV stores an HTML snippet in the 'VISUAL CODE' column.
    We extract the first <img src="..."> and first <a href="...">.
    """
    s = visual_code_html or ""
    img = None
    url = None

    m_img = re.search(r'<img[^>]+src\s*=\s*"([^"]+)"', s, flags=re.IGNORECASE)
    if m_img:
        img = m_img.group(1).strip()

    m_a = re.search(r'<a[^>]+href\s*=\s*"([^"]+)"', s, flags=re.IGNORECASE)
    if m_a:
        url = m_a.group(1).strip()

    return img or None, url or None


def load_products_from_template_csv(path: str | Path) -> list[Product]:
    p = Path(path)
    with p.open("r", newline="", encoding="utf-8-sig") as f:
        # Template CSV includes a grouping row above the real header.
        # We scan until we find the real header containing "Product Name".
        raw = f.read()

    lines = raw.splitlines(True)
    header_idx = None
    for i, line in enumerate(lines):
        if "Product Name" in line and "SKU" in line and "Role Type" in line:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Could not locate catalog header row in CSV: {p}")

    with p.open("r", newline="", encoding="utf-8-sig") as f2:
        # Rewind by reopening and skipping lines up to header
        for _ in range(header_idx):
            f2.readline()
        reader = csv.DictReader(f2)
        products: list[Product] = []

        for row in reader:
            name = (row.get("Product Name") or "").strip()
            sku = (row.get("SKU") or "").strip()
            visual_code = (row.get("VISUAL CODE") or "").strip()
            category = (row.get("Category") or "").strip()
            primary_function = (row.get("Primary Function") or "").strip()
            role_raw = (row.get("Role Type") or "").strip()

            if not name or not sku:
                continue

            role_type = _infer_role_type(sku, category, role_raw, primary_function, name)

            problem_scores = {k: _to_float(row.get(col), 0.0) for k, col in _PROBLEM_COLS.items()}
            soil_scores = {k: _to_float(row.get(col), 0.0) for k, col in _SOIL_COLS.items()}
            use_case_scores = {k: _to_float(row.get(col), 0.0) for k, col in _USE_CASE_COLS.items()}
            lawn_goal_scores = {k: _to_float(row.get(col), 0.0) for k, col in LAWN_GOAL_COLS.items()}
            garden_goal_scores = {k: _to_float(row.get(col), 0.0) for k, col in GARDEN_GOAL_COLS.items()}
            farm_goal_scores = {k: _to_float(row.get(col), 0.0) for k, col in FARM_GOAL_COLS.items()}
            seasonal_scores = {season: _to_float(row.get(col), 0.0) for season, col in _SEASON_COLS.items()}

            blob = _norm(" ".join([name, category, primary_function, role_raw]))
            is_iron_sulphate = sku == "846" or ("iron sulphate" in blob) or ("ferrous sulphate" in blob)
            is_lime_based = sku in ("LIMEGr", "DOL") or "lime" in blob or "dolomite" in blob
            is_iron_based = sku in _LIQUID_IRON_SKUS or is_iron_sulphate
            contains_iron = sku in _CONTAINS_IRON_SKUS or is_iron_based
            is_iron_chelate = sku in _CHELATE_SKUS or ("chelate" in blob and "iron" in blob)
            is_gypsum = sku in _GYPSUM_SKUS or "gypsum" in blob
            is_wetter = sku in _WETTER_SKUS or (
                role_type != RoleType.BUNDLE
                and ("soil wetter" in blob or "wetting agent" in blob)
            )
            is_high_nitrogen = sku in _HIGH_N_SKUS
            is_incompatible_with_iron = sku in _IRON_INCOMPATIBLE_SKUS
            is_lawn_specialist = sku in _LAWN_SPECIALIST_SKUS
            is_core_range = sku in _CORE_RANGE_SKUS
            is_garden_reproductive = sku in _GARDEN_REPRODUCTIVE_SKUS or (
                "flowers" in blob and "fruit" in blob
            )
            # Garden-bed lines were given lawn-goal scores in the spreadsheet.
            # Keep them off turf ranking so lawn stays primary without hiding garden SKUs.
            if sku == "1156":
                lawn_goal_scores = {k: min(float(v), 1.0) for k, v in lawn_goal_scores.items()}
            # Dual-use biostimulants — lawn and garden.
            if sku in ("STM", "29800"):
                use_case_scores["lawn"] = 1.0
                use_case_scores["garden_beds"] = 1.0
            is_garden_specialist = (
                (not is_lawn_specialist)
                and float(use_case_scores.get("lawn", 0.0)) <= 0
                and float(use_case_scores.get("garden_beds", 0.0)) >= 1
            )

            improves_soil_structure = (
                role_type == RoleType.SOIL_STRUCTURE or is_gypsum or is_wetter or ("zeolite" in blob)
            )
            improves_biology = role_type == RoleType.BIOLOGY or any(
                k in blob for k in ["seaweed", "kelp", "inocul", "microb", "worm", "castings", "vermic"]
            )
            improves_uptake = role_type == RoleType.UPTAKE or any(
                k in blob for k in ["fulvic", "humic", "chelat"]
            )
            improves_fertiliser_efficiency = any(k in blob for k in ["zeolite", "humic", "fulvic"])
            improves_water_infiltration = is_wetter or any(
                k in blob for k in ["hydrophobic", "infiltration"]
            )
            improves_visual_greening = role_type == RoleType.VISUAL or contains_iron

            image_url, product_url = _extract_visual_assets(visual_code)

            products.append(
                Product(
                    id=sku,
                    name=name,
                    category=category,
                    role_type=role_type,
                    image_url=image_url,
                    product_url=product_url,
                    problem_scores=problem_scores,  # type: ignore[arg-type]
                    soil_scores=soil_scores,  # type: ignore[arg-type]
                    use_case_scores=use_case_scores,  # type: ignore[arg-type]
                    lawn_goal_scores=lawn_goal_scores,
                    garden_goal_scores=garden_goal_scores,
                    farm_goal_scores=farm_goal_scores,
                    seasonal_scores=seasonal_scores,
                    improves_soil_structure=improves_soil_structure,
                    improves_biology=improves_biology,
                    improves_uptake=improves_uptake,
                    improves_fertiliser_efficiency=improves_fertiliser_efficiency,
                    improves_water_infiltration=improves_water_infiltration,
                    improves_visual_greening=improves_visual_greening,
                    is_iron_based=is_iron_based,
                    contains_iron=contains_iron,
                    is_iron_chelate=is_iron_chelate,
                    is_lime_based=is_lime_based,
                    is_iron_sulphate=is_iron_sulphate,
                    is_gypsum=is_gypsum,
                    is_wetter=is_wetter,
                    is_high_nitrogen=is_high_nitrogen,
                    is_incompatible_with_iron=is_incompatible_with_iron,
                    is_lawn_specialist=is_lawn_specialist,
                    is_garden_reproductive=is_garden_reproductive,
                    is_garden_specialist=is_garden_specialist,
                    is_core_range=is_core_range,
                    short_reason=(row.get("Short Recommendation Reason") or "").strip() or None,
                    problem_explanation=(row.get("Problem Explanation") or "").strip() or None,
                    why_this_works=(row.get("Why This Works") or "").strip() or None,
                    app_logic_notes=(row.get("App Logic considerations") or "").strip() or None,
                )
            )

    return products


@dataclass(frozen=True)
class Catalog:
    products: list[Product]

    @classmethod
    def from_csv(cls, path: str | Path) -> "Catalog":
        return cls(products=load_products_from_template_csv(path))

    def by_role(self, role: RoleType) -> list[Product]:
        return [p for p in self.products if p.role_type == role]


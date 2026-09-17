from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class RoleType(str, Enum):
    SOIL_STRUCTURE = "soil_structure"
    SOIL_CHEMISTRY = "soil_chemistry"
    BIOLOGY = "biology"
    UPTAKE = "uptake"
    NUTRITION = "nutrition"
    VISUAL = "visual"
    BUNDLE = "bundle"


Intent = Literal[
    "rescue_mode",
    "maintenance_mode",
    "performance_mode",
    "establishment_mode",
    "diagnosis_mode",
]

Season = Literal["spring", "summer", "autumn", "winter", "unknown"]

ProblemKey = Literal[
    "yellowing",
    "slow_growth",
    "weak_roots",
    "nutrient_lockout",
    "patchy_lawn",
    "compaction",
    "poor_water_retention",
    "fungal_issues",
    "poor_flowering",
]

SoilKey = Literal[
    "sandy",
    "clay",
    "acidic",
    "alkaline",
    "low_organic_matter",
    "hydrophobic",
]

UseCaseKey = Literal["lawn", "garden_beds", "indoor_plants", "pots", "farms"]

RecommendationMode = Literal["problems", "goals"]
GoalVertical = Literal["lawn", "garden", "farm"]
PhMethod = Literal["water", "cacl2"]


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    category: str
    role_type: RoleType

    image_url: str | None = None
    product_url: str | None = None

    problem_scores: dict[ProblemKey, float] = field(default_factory=dict)
    soil_scores: dict[SoilKey, float] = field(default_factory=dict)
    use_case_scores: dict[UseCaseKey, float] = field(default_factory=dict)
    lawn_goal_scores: dict[str, float] = field(default_factory=dict)
    garden_goal_scores: dict[str, float] = field(default_factory=dict)
    farm_goal_scores: dict[str, float] = field(default_factory=dict)
    seasonal_scores: dict[Season, float] = field(default_factory=dict)

    improves_soil_structure: bool = False
    improves_biology: bool = False
    improves_uptake: bool = False
    improves_fertiliser_efficiency: bool = False
    improves_water_infiltration: bool = False
    improves_visual_greening: bool = False

    # Soluble/liquid iron — do not tank-mix with humic/seaweed/wetter
    is_iron_based: bool = False
    # Includes granular Fe (CHAMPION) for chlorosis credit without tank-mix rules
    contains_iron: bool = False
    is_iron_chelate: bool = False
    is_lime_based: bool = False
    is_iron_sulphate: bool = False
    is_gypsum: bool = False
    is_wetter: bool = False
    is_high_nitrogen: bool = False
    is_incompatible_with_iron: bool = False
    is_lawn_specialist: bool = False
    is_garden_reproductive: bool = False
    is_garden_specialist: bool = False
    # Lawn Lovers Starter + Pro pack SKUs — default recommendable range
    is_core_range: bool = False

    short_reason: str | None = None
    problem_explanation: str | None = None
    why_this_works: str | None = None
    app_logic_notes: str | None = None


@dataclass(frozen=True)
class UserInput:
    intent: Intent
    season: Season = "unknown"
    use_case: UseCaseKey | None = None

    recommendation_mode: RecommendationMode = "problems"
    goal_vertical: GoalVertical | None = None
    goal_weights: dict[str, float] = field(default_factory=dict)

    problems: dict[ProblemKey, float] = field(default_factory=dict)
    soils: dict[SoilKey, float] = field(default_factory=dict)

    confidence: float = 0.6

    # Optional lab/home soil test — overrides acidic/alkaline/OM guesses when set
    soil_ph: float | None = None
    soil_ph_method: PhMethod = "water"
    organic_matter_pct: float | None = None
    soil_test_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoredProduct:
    product: Product
    score: float
    breakdown: dict[str, float]
    reasons: list[str]


@dataclass(frozen=True)
class Recommendation:
    intent: Intent
    season: Season
    primary: Product
    stack: list[Product]
    upgrade_path: list[Product]
    explanations: dict[str, object]
    primary_fertiliser: Product | None = None

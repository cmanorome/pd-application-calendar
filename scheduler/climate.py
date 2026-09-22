from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

RegionId = Literal["south", "north", "east_coast"]


@dataclass(frozen=True)
class Region:
    id: RegionId
    label: str
    winter_months: frozenset[int]
    growing_months: frozenset[int]
    winter_note: str


ALL_MONTHS = frozenset(range(1, 13))

REGIONS: dict[str, Region] = {
    "south": Region(
        id="south",
        label="Southern Australia",
        winter_months=frozenset({6, 7, 8}),
        growing_months=frozenset({9, 10, 11, 12, 1, 2, 3, 4}),
        winter_note=(
            "Keep applying through winter, just less often. Winter means nights below 10°C — "
            "usually June to August in southern Australia, and shorter or sometimes missing in the north."
        ),
    ),
    "east_coast": Region(
        id="east_coast",
        label="East coast Australia",
        winter_months=frozenset({6, 7}),
        growing_months=frozenset({8, 9, 10, 11, 12, 1, 2, 3, 4, 5}),
        winter_note=(
            "Keep applying through winter, just less often. On the east coast winter is shorter — "
            "usually June and July, when nights dip below 10°C."
        ),
    ),
    "north": Region(
        id="north",
        label="Northern Australia",
        winter_months=frozenset(),
        growing_months=ALL_MONTHS,
        winter_note=(
            "Nights rarely drop below 10°C in the north, so this plan keeps the usual cadence year-round."
        ),
    ),
}

# Southern windows stay the default when the field is left blank.
CLIMATE_LABEL = REGIONS["south"].label
GROWING_MONTHS = REGIONS["south"].growing_months
WINTER_MONTHS = REGIONS["south"].winter_months
SUMMER_MONTHS = frozenset({12, 1, 2})

_ALIASES = {
    "": "south",
    "temperate": "south",
    "southern": "south",
    "southern_australia": "south",
    "south_australia": "south",
    "northern": "north",
    "north_tropics": "north",
    "tropics": "north",
    "tropical": "north",
    "east": "east_coast",
    "eastcoast": "east_coast",
    "east_coast": "east_coast",
    "subtropical": "east_coast",
    "sub_tropical": "east_coast",
}


def parse_region(value: object) -> Region:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    key = _ALIASES.get(raw, raw)
    return REGIONS.get(key, REGIONS["south"])


def season_for(day: date) -> str:
    if day.month in (9, 10, 11):
        return "spring"
    if day.month in (12, 1, 2):
        return "summer"
    if day.month in (3, 4, 5):
        return "autumn"
    return "winter"


def in_growing_season(day: date, region: Region | str | None = None) -> bool:
    loc = region if isinstance(region, Region) else parse_region(region)
    return day.month in loc.growing_months


def in_winter(day: date, region: Region | str | None = None) -> bool:
    loc = region if isinstance(region, Region) else parse_region(region)
    return day.month in loc.winter_months


def in_summer(day: date) -> bool:
    return day.month in SUMMER_MONTHS

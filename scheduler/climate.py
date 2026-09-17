from __future__ import annotations

from datetime import date
from typing import Literal

Climate = Literal["temperate"]

CLIMATE_LABEL = "Temperate / southern Australia"

# Warm-season turf growing window used for Champion, MaxGreen, Lawn Envy, etc.
GROWING_MONTHS = frozenset({9, 10, 11, 12, 1, 2, 3, 4})
WINTER_MONTHS = frozenset({6, 7, 8})
SUMMER_MONTHS = frozenset({12, 1, 2})


def season_for(day: date) -> str:
    if day.month in (9, 10, 11):
        return "spring"
    if day.month in (12, 1, 2):
        return "summer"
    if day.month in (3, 4, 5):
        return "autumn"
    return "winter"


def in_growing_season(day: date) -> bool:
    return day.month in GROWING_MONTHS


def in_winter(day: date) -> bool:
    return day.month in WINTER_MONTHS


def in_summer(day: date) -> bool:
    return day.month in SUMMER_MONTHS

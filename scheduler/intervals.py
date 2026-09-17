from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Interval:
    sku: str
    cadence_days: int
    one_off: bool
    window: str
    max_per_year: int
    tank_group: str
    method: str
    how_often: str
    notes: str


_ROLE_FALLBACK: dict[str, tuple[int, bool, str, int, str, str, str]] = {
    "biology": (14, False, "year_round", 24, "mixable", "spray", "Every 2 weeks"),
    "uptake": (14, False, "year_round", 24, "mixable", "spray", "Every 2 weeks"),
    "nutrition": (28, False, "growing_season", 10, "no_iron_mix", "spray", "Every 4 weeks in the growing season"),
    "visual": (28, False, "growing_season", 8, "iron", "spray", "Every 4 weeks in the growing season"),
    "soil_structure": (365, True, "year_round", 1, "granular", "spread", "Once at the start of the plan"),
    "soil_chemistry": (365, True, "year_round", 1, "granular", "spread", "Once at the start of the plan"),
    "bundle": (0, True, "year_round", 0, "granular", "spread", "See kit contents"),
}


class IntervalTable:
    def __init__(self, rows: dict[str, Interval]):
        self._rows = rows

    @classmethod
    def from_csv(cls, path: str | Path) -> "IntervalTable":
        rows: dict[str, Interval] = {}
        with Path(path).open("r", newline="", encoding="utf-8-sig") as f:
            for raw in csv.DictReader(f):
                sku = (raw.get("sku") or "").strip()
                if not sku:
                    continue
                rows[sku.upper()] = Interval(
                    sku=sku.upper(),
                    cadence_days=int(raw.get("cadence_days") or 28),
                    one_off=(raw.get("one_off") or "0").strip() in {"1", "true", "yes"},
                    window=(raw.get("window") or "growing_season").strip(),
                    max_per_year=int(raw.get("max_per_year") or 8),
                    tank_group=(raw.get("tank_group") or "mixable").strip(),
                    method=(raw.get("method") or "spray").strip(),
                    how_often=(raw.get("how_often") or "").strip(),
                    notes=(raw.get("notes") or "").strip(),
                )
        return cls(rows)

    def for_product(self, sku: str, role_type: str) -> Interval:
        found = self._rows.get((sku or "").upper())
        if found:
            return found
        fb = _ROLE_FALLBACK.get(role_type, _ROLE_FALLBACK["nutrition"])
        return Interval(
            sku=(sku or "").upper(),
            cadence_days=fb[0],
            one_off=fb[1],
            window=fb[2],
            max_per_year=fb[3],
            tank_group=fb[4],
            method=fb[5],
            how_often=fb[6],
            notes="Typical Plant Doctor cadence for this product type.",
        )

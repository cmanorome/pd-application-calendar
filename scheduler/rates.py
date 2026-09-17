from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _parse_qty(value: str | None) -> tuple[float | None, str]:
    if not value:
        return None, ""
    cleaned = value.replace(",", "").strip()
    match = re.search(r"(-?\d+(?:\.\d+)?)", cleaned)
    if not match:
        return None, ""
    number = float(match.group(1))
    unit = cleaned[match.end() :].strip().lower()
    if "ml" in unit or unit == "ml":
        unit = "mL"
    elif unit.startswith("l") and "ml" not in unit:
        unit = "L"
    elif "kg" in unit:
        unit = "kg"
    elif unit.startswith("g"):
        unit = "g"
    else:
        unit = unit or ""
    return number, unit


def _fmt(value: float, unit: str) -> str:
    rounded = round(value, 2)
    if unit == "mL" and rounded >= 1000:
        litres = round(rounded / 1000, 2)
        return f"{_trim(rounded)} mL ({_trim(litres)} L)"
    return f"{_trim(rounded)} {unit}".strip()


def _trim(value: float) -> str:
    if abs(value - round(value)) < 0.005:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class RateHint:
    sku: str
    plant_type: str
    min_ml_100m2: float | None
    max_ml_100m2: float | None
    min_kg_100m2: float | None
    max_kg_100m2: float | None
    min_g_m2: float | None
    max_g_m2: float | None
    product_url: str
    pack_sizes: list[str]


@dataclass(frozen=True)
class AppliedRate:
    per_100m2: str
    for_area: str | None
    product_url: str
    pack_sizes: list[str]


class RateBook:
    def __init__(self, rows: list[RateHint]):
        self._rows = rows

    @classmethod
    def from_csv(cls, path: str | Path) -> "RateBook":
        rows: list[RateHint] = []
        with Path(path).open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            raw_headers = next(reader, [])
            headers = [_norm_header(h) for h in raw_headers]
            for raw in reader:
                if not raw or not any(c.strip() for c in raw):
                    continue
                rec: dict[str, list[str]] = {}
                for i, key in enumerate(headers):
                    val = raw[i].strip() if i < len(raw) else ""
                    rec.setdefault(key, []).append(val)

                def first(*keys: str) -> str:
                    for k in keys:
                        for v in rec.get(k, []):
                            if v:
                                return v
                    return ""

                sku = first("sku")
                if not sku:
                    continue
                packs = [v for v in rec.get("unitsize", []) if v]
                min_ml, _ = _parse_qty(first("rateminml100m2", "rateminml100m"))
                max_ml, _ = _parse_qty(first("ratemaxml100m2", "ratemaxml100m"))
                min_kg, _ = _parse_qty(first("rateminkg100m2", "rateminkg100m"))
                max_kg, _ = _parse_qty(first("ratemaxkg100m2", "ratemaxkg100m"))
                min_g, _ = _parse_qty(first("ratemingm2", "ratemingm"))
                max_g, _ = _parse_qty(first("ratemaxgm2", "ratemaxgm"))
                rows.append(
                    RateHint(
                        sku=sku.upper(),
                        plant_type=first("planttype"),
                        min_ml_100m2=min_ml,
                        max_ml_100m2=max_ml,
                        min_kg_100m2=min_kg,
                        max_kg_100m2=max_kg,
                        min_g_m2=min_g,
                        max_g_m2=max_g,
                        product_url=first("buynow"),
                        pack_sizes=packs,
                    )
                )
        return cls(rows)

    def for_sku(self, sku: str, *, lawn: bool, area_m2: float | None) -> AppliedRate | None:
        matches = [r for r in self._rows if r.sku == (sku or "").upper()]
        if not matches:
            return None

        def score(row: RateHint) -> int:
            pt = (row.plant_type or "").lower()
            n = 0
            if lawn and "grass" in pt:
                n += 5
            if not lawn and any(k in pt for k in ("bedding", "garden", "home garden", "general")):
                n += 4
            if row.min_ml_100m2 or row.max_ml_100m2 or row.min_kg_100m2 or row.max_kg_100m2:
                n += 2
            return n

        row = sorted(matches, key=score, reverse=True)[0]
        per, unit = self._range(row)
        if not per:
            return AppliedRate(per_100m2="", for_area=None, product_url=row.product_url, pack_sizes=row.pack_sizes)
        per_label = f"{per} per 100 m²"
        for_area = None
        if area_m2 and area_m2 > 0:
            factor = area_m2 / 100.0
            for_area = self._scale(row, factor, area_m2)
        return AppliedRate(
            per_100m2=per_label,
            for_area=for_area,
            product_url=row.product_url,
            pack_sizes=row.pack_sizes,
        )

    def _range(self, row: RateHint) -> tuple[str, str]:
        if row.min_ml_100m2 or row.max_ml_100m2:
            return self._pair(row.min_ml_100m2, row.max_ml_100m2, "mL"), "mL"
        if row.min_kg_100m2 or row.max_kg_100m2:
            return self._pair(row.min_kg_100m2, row.max_kg_100m2, "kg"), "kg"
        if row.min_g_m2 or row.max_g_m2:
            min_g = row.min_g_m2 * 100 if row.min_g_m2 else None
            max_g = row.max_g_m2 * 100 if row.max_g_m2 else None
            return self._pair(min_g, max_g, "g"), "g"
        return "", ""

    def _scale(self, row: RateHint, factor: float, area_m2: float) -> str:
        if row.min_ml_100m2 or row.max_ml_100m2:
            return f"{self._pair(_mul(row.min_ml_100m2, factor), _mul(row.max_ml_100m2, factor), 'mL')} for {_trim(area_m2)} m²"
        if row.min_kg_100m2 or row.max_kg_100m2:
            return f"{self._pair(_mul(row.min_kg_100m2, factor), _mul(row.max_kg_100m2, factor), 'kg')} for {_trim(area_m2)} m²"
        if row.min_g_m2 or row.max_g_m2:
            return f"{self._pair(_mul(row.min_g_m2, area_m2), _mul(row.max_g_m2, area_m2), 'g')} for {_trim(area_m2)} m²"
        return ""

    @staticmethod
    def _pair(lo: float | None, hi: float | None, unit: str) -> str:
        if lo is not None and hi is not None and abs(lo - hi) > 0.05:
            return f"{_fmt(lo, unit)}–{_fmt(hi, unit)}"
        if hi is not None:
            return _fmt(hi, unit)
        if lo is not None:
            return _fmt(lo, unit)
        return ""


def _mul(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    return value * factor

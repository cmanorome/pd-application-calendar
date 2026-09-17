from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pd_engine.types import Product, RoleType

from .climate import CLIMATE_LABEL, in_growing_season, in_summer, season_for
from .intervals import Interval, IntervalTable
from .rates import RateBook

LIME_WAIT_DAYS = 42
IRON_GAP_DAYS = 3
HORIZON_DAYS = 365
MAX_EVENTS = 180

DISCLAIMER = (
    "Typical temperate / southern Australia program for warm-season lawns and home gardens. "
    "Adjust to growth, weather, and the label. This is not a prescription."
)


def _product_dict(p: Product) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "category": p.category,
        "role_type": p.role_type.value,
        "image_url": getattr(p, "image_url", None),
        "product_url": getattr(p, "product_url", None),
        "short_reason": getattr(p, "short_reason", None),
        "is_iron_based": bool(getattr(p, "is_iron_based", False)),
        "is_lime_based": bool(getattr(p, "is_lime_based", False)),
        "is_high_nitrogen": bool(getattr(p, "is_high_nitrogen", False)),
        "is_incompatible_with_iron": bool(getattr(p, "is_incompatible_with_iron", False)),
    }


def _short_name(product: Product) -> str:
    name = (product.name or "").strip()
    if "(" in name:
        name = name.split("(")[0].strip()
    return name or "This product"


def program_products_from_catalog(
    rec,
    catalog_products: list[Product],
    *,
    wants_lime: bool = False,
) -> tuple[list[Product], list[str]]:
    notes: list[str] = []
    by_id = {p.id: p for p in catalog_products}
    products: list[Product] = []
    seen: set[str] = set()

    def add(p: Product | None) -> None:
        if p is None or p.id in seen or p.role_type == RoleType.BUNDLE:
            return
        seen.add(p.id)
        products.append(p)

    for p in rec.stack:
        add(p)
    add(rec.primary_fertiliser)

    champ = (rec.explanations or {}).get("champion_turf_pair") if rec.explanations else None
    if champ:
        add(by_id.get("886"))
        notes.append(
            "Champion Fairway is on the calendar for everyday lawns. Swap to Greens Grade if you keep a low-cut surface."
        )
        if "892" in seen and "886" in seen:
            products = [p for p in products if p.id != "892"]
            seen.discard("892")

    # The same-week stack cannot mix lime and iron. A year calendar can: lime first, iron later.
    if wants_lime and not any(p.is_lime_based for p in products):
        add(by_id.get("LIMEGr"))
        notes.append("Lime is first. Wait 6 weeks before iron so pH can move.")

    return products, notes


def _first_ok(start: date, interval: Interval, product: Product, *, fungal: bool) -> date | None:
    day = start
    for _ in range(HORIZON_DAYS):
        if _date_allowed(day, interval, product, fungal=fungal):
            return day
        day += timedelta(days=1)
    return None


def _date_allowed(day: date, interval: Interval, product: Product, *, fungal: bool) -> bool:
    if interval.window == "growing_season" and not in_growing_season(day):
        return False
    if product.is_high_nitrogen and fungal and in_summer(day):
        return False
    return True


def _start_offset(product: Product, interval: Interval, others: list[Product]) -> int:
    has_lime = any(p.is_lime_based for p in others) or product.is_lime_based
    has_iron = any(p.is_iron_based for p in others) or product.is_iron_based
    if product.is_lime_based or product.role_type in (RoleType.SOIL_STRUCTURE, RoleType.SOIL_CHEMISTRY):
        return 0
    if product.is_iron_based:
        wait = IRON_GAP_DAYS if any(p.is_incompatible_with_iron for p in others) else 0
        if has_lime:
            wait = max(wait, LIME_WAIT_DAYS)
        return wait
    if interval.tank_group == "no_iron_mix" and has_iron:
        return IRON_GAP_DAYS
    return 0


def _place_dates(
    start: date,
    interval: Interval,
    product: Product,
    *,
    fungal: bool,
    offset: int,
) -> list[date]:
    first = _first_ok(start + timedelta(days=offset), interval, product, fungal=fungal)
    if first is None:
        return []
    if interval.one_off or interval.cadence_days <= 0 or interval.max_per_year <= 1:
        return [first]

    out = [first]
    day = first
    end = start + timedelta(days=HORIZON_DAYS)
    while len(out) < interval.max_per_year:
        day = day + timedelta(days=interval.cadence_days)
        if day >= end:
            break
        if _date_allowed(day, interval, product, fungal=fungal):
            out.append(day)
            continue
        # Skip closed windows (winter / fungal summer) and resume when allowed.
        resumed = _first_ok(day, interval, product, fungal=fungal)
        if resumed is None or resumed >= end:
            break
        if resumed != day:
            day = resumed
        out.append(day)
    return out


def _resolve_same_day(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep iron off the same day as seaweed / humic / wetter / Activ8."""
    by_date: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_date.setdefault(ev["date"], []).append(ev)

    moved: list[dict[str, Any]] = []
    for ev in events:
        if ev["tank_group"] != "iron":
            moved.append(ev)
            continue
        d = date.fromisoformat(ev["date"])
        for _ in range(10):
            clash = any(
                p.get("blocks_iron")
                for p in by_date.get(d.isoformat(), [])
                if p["sku"] != ev["sku"]
            )
            if not clash:
                ev = {**ev, "date": d.isoformat()}
                break
            d += timedelta(days=1)
        moved.append(ev)

    moved.sort(key=lambda e: (e["date"], e["name"]))
    return moved[:MAX_EVENTS]


def place_warnings(products: list[Product], *, lawn: bool) -> list[str]:
    notes: list[str] = []
    for product in products:
        name = _short_name(product)
        if lawn and product.is_garden_reproductive:
            notes.append(f"{name} is a garden flower/fruit feed, not a lawn fertiliser.")
        if (not lawn) and product.is_lawn_specialist:
            notes.append(f"{name} is a turf product — not the usual garden feed.")
    return notes


def build_calendar(
    products: list[Product],
    *,
    intervals: IntervalTable,
    rates: RateBook,
    start: date,
    area_m2: float | None,
    lawn: bool,
    fungal: bool,
    extra_notes: list[str] | None = None,
    choice_summary: list[str] | None = None,
) -> dict[str, Any]:
    ids = [p.id for p in products]
    others_for = {p.id: [x for x in products if x.id != p.id] for p in products}

    events: list[dict[str, Any]] = []
    product_cards: list[dict[str, Any]] = []

    for product in products:
        interval = intervals.for_product(product.id, product.role_type.value)
        offset = _start_offset(product, interval, others_for[product.id])
        dates = _place_dates(start, interval, product, fungal=fungal, offset=offset)
        rate = rates.for_sku(product.id, lawn=lawn, area_m2=area_m2)
        rate_label = (rate.per_100m2 if rate else "") or ""
        amount_label = (rate.for_area if rate else None)
        url = product.product_url or (rate.product_url if rate else None)
        card = _product_dict(product)
        card.update(
            {
                "how_often": interval.how_often,
                "method": interval.method,
                "tank_group": interval.tank_group,
                "rate_label": rate_label,
                "amount_label": amount_label,
                "schedule_notes": interval.notes,
                "product_url": url,
                "pack_sizes": rate.pack_sizes if rate else [],
                "applications": len(dates),
            }
        )
        product_cards.append(card)

        blocks_iron = product.is_incompatible_with_iron or interval.tank_group == "no_iron_mix"
        for d in dates:
            note_bits = [interval.notes]
            if amount_label:
                note_bits.insert(0, amount_label)
            elif rate_label:
                note_bits.insert(0, rate_label)
            events.append(
                {
                    "date": d.isoformat(),
                    "sku": product.id,
                    "name": _short_name(product),
                    "full_name": product.name,
                    "role": product.role_type.value,
                    "how_often": interval.how_often,
                    "rate_label": rate_label,
                    "amount_label": amount_label,
                    "notes": " ".join(b for b in note_bits if b),
                    "product_url": url,
                    "image_url": product.image_url,
                    "method": interval.method,
                    "tank_group": interval.tank_group,
                    "blocks_iron": blocks_iron,
                }
            )

    events = _resolve_same_day(events)

    all_notes = list(extra_notes or []) + place_warnings(products, lawn=lawn)
    if any(e["tank_group"] == "iron" for e in events) and any(e.get("blocks_iron") for e in events):
        all_notes.append(
            "Liquid iron is on a different day from seaweed, humic, wetter, and Activ8 — do not mix them in the same sprayer. Stimulizer can tank-mix with iron."
        )

    return {
        "climate": "temperate",
        "climate_label": CLIMATE_LABEL,
        "disclaimer": DISCLAIMER,
        "start_date": start.isoformat(),
        "season": season_for(start),
        "lawn": lawn,
        "area_m2": area_m2,
        "products": product_cards,
        "events": events,
        "notes": [n for n in all_notes if n],
        "choice_summary": list(choice_summary or []),
        "product_ids": ids,
    }

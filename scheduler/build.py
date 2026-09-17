from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pd_engine.types import Product, RoleType

from .climate import CLIMATE_LABEL, in_growing_season, in_summer, season_for
from .intervals import Interval, IntervalTable, usage_labels
from .rates import RateBook

LIME_WAIT_DAYS = 42
IRON_GAP_DAYS = 3
MIX_SNAP_DAYS = 7
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


def _is_tank_mix(interval: Interval) -> bool:
    """Liquids the usage guide says can be mixed together as concentrates."""
    if interval.tank_group in {"iron", "granular"}:
        return False
    method = (interval.method or "").lower().replace("_", "-")
    if method in {"spread", "hose-on"}:
        return False
    return bool((interval.usage or {}).get("mix_together"))


def _product_blocks_iron(product: Product, interval: Interval) -> bool:
    if product.is_iron_based or interval.tank_group == "iron":
        return False
    if (interval.usage or {}).get("mix_with_iron"):
        return False
    return (
        product.is_incompatible_with_iron
        or interval.tank_group == "no_iron_mix"
        or _is_tank_mix(interval)
    )


def _start_offset(
    product: Product,
    interval: Interval,
    others: list[Product],
    *,
    others_block_iron: bool,
) -> int:
    has_lime = any(p.is_lime_based for p in others) or product.is_lime_based
    if product.is_lime_based or product.role_type in (RoleType.SOIL_STRUCTURE, RoleType.SOIL_CHEMISTRY):
        return 0
    if _is_tank_mix(interval):
        return 0
    if product.is_iron_based or interval.tank_group == "iron":
        wait = IRON_GAP_DAYS if others_block_iron else 0
        if has_lime:
            wait = max(wait, LIME_WAIT_DAYS)
        return wait
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


def _coalesce_tank_mix(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Put mix-as-concentrate sprays on the same visit as the main spray cadence."""
    mix = [e for e in events if e.get("tank_mix")]
    rest = [e for e in events if not e.get("tank_mix")]
    if len({e["sku"] for e in mix}) < 2:
        return events

    sku_counts: dict[str, int] = {}
    for e in mix:
        sku_counts[e["sku"]] = sku_counts.get(e["sku"], 0) + 1
    anchor_sku = max(sku_counts, key=lambda s: sku_counts[s])
    anchors = sorted({date.fromisoformat(e["date"]) for e in mix if e["sku"] == anchor_sku})
    if not anchors:
        return events

    def snap_to_anchor(d: date) -> date:
        nearby = [a for a in anchors if abs((a - d).days) <= MIX_SNAP_DAYS]
        if nearby:
            return min(nearby, key=lambda a: (abs((a - d).days), a))
        later = [a for a in anchors if a >= d]
        if later:
            return later[0]
        return anchors[-1]

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ev in mix:
        target = snap_to_anchor(date.fromisoformat(ev["date"])).isoformat()
        key = (ev["sku"], target)
        if key in seen:
            continue
        seen.add(key)
        merged.append({**ev, "date": target})
    return rest + merged


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
    interval_for = {p.id: intervals.for_product(p.id, p.role_type.value) for p in products}
    others_block_iron = any(_product_blocks_iron(p, interval_for[p.id]) for p in products)

    events: list[dict[str, Any]] = []
    product_cards: list[dict[str, Any]] = []

    for product in products:
        interval = interval_for[product.id]
        tank_mix = _is_tank_mix(interval)
        offset = _start_offset(
            product,
            interval,
            others_for[product.id],
            others_block_iron=others_block_iron,
        )
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
                "tank_mix": tank_mix,
                "usage": dict(interval.usage),
                "usage_labels": usage_labels(interval.usage),
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
                    "tank_mix": tank_mix,
                    "usage": dict(interval.usage),
                    "usage_labels": usage_labels(interval.usage),
                    "blocks_iron": blocks_iron,
                }
            )

    events = _coalesce_tank_mix(events)
    events = _resolve_same_day(events)
    counts: dict[str, int] = {}
    for ev in events:
        counts[ev["sku"]] = counts.get(ev["sku"], 0) + 1
    for card in product_cards:
        card["applications"] = counts.get(card["id"], 0)

    all_notes = list(extra_notes or []) + place_warnings(products, lawn=lawn)
    mix_names = []
    seen_mix: set[str] = set()
    for ev in events:
        if ev.get("tank_mix") and ev["sku"] not in seen_mix:
            seen_mix.add(ev["sku"])
            mix_names.append(ev["name"])
    if len(mix_names) >= 2:
        all_notes.append(
            "Mix these as concentrates in one sprayer on the same day: "
            + ", ".join(mix_names)
            + ". Jar test if it is a new combination."
        )
    if any(e["tank_group"] == "iron" for e in events) and any(e.get("blocks_iron") for e in events):
        all_notes.append(
            "Liquid iron is on a different day from seaweed, humic, wetter, and Activ8 — do not mix them in the same sprayer. Stimulizer can tank-mix with iron, but is kept with the other concentrates so you only spray once."
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

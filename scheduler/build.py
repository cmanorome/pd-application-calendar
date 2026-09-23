from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pd_engine.catalog import LAWN_LOVERS_PRO_SKUS
from pd_engine.types import Product, RoleType

from .climate import Region, in_growing_season, in_summer, in_winter, parse_region, season_for
from .intervals import Interval, IntervalTable, usage_labels
from .rates import RateBook

LIME_WAIT_DAYS = 42
IRON_GAP_DAYS = 3
MIX_SNAP_DAYS = 7
MAX_EVENTS = 500
_PLACE_CAP = 40
_FFR_LIQUID = "721"
_FFR_GRANULAR = "575"
_RSL_GRANULAR = "1156"
_ACTIV8 = ("A8M", "A8X")
_NOTE_NAMES = {
    "A8X": "Activ8EXTRA",
    "A8M": "Activ8Mate",
    "SWS": "Seaweed Secrets",
    "STM": "Stimulizer",
    "29800": "Quantum H",
    "NSWL": "Soil Wetter Liquid",
    "721": "Flowers, Fruits & Roots",
    "LIR": "Liquid Iron",
    "LEN": "Lawn Envy",
    "886": "Champion Fairway",
    "414": "Fulvic Acid",
}


def _calendar_end(start: date) -> date:
    """Exclusive end of the 12-month view (first of the start month, next year)."""
    return date(start.year + 1, start.month, 1)


DISCLAIMER = (
    "Typical program for warm-season lawns and home gardens in Australia. "
    "Adjust to growth, weather, and the label. This is not a prescription."
)
WEED_CONTROL_URL = "https://www.plantdoctor.com.au/weed-and-pest-control"
WEED_SUPPRESSION_NOTE = (
    "This plan does not include chemical weed killers. We support thicker, healthier growth "
    "so lawns and gardens can crowd weeds out. Chemical products are on "
    f"{WEED_CONTROL_URL}"
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


def _note_name(sku: str, fallback: str = "") -> str:
    return _NOTE_NAMES.get(sku) or fallback or sku


def _is_iron_spacing_note(text: str) -> bool:
    blob = (text or "").lower()
    return "iron" in blob and "different day" in blob


def _join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def prefer_single_ffr(products: list[Product]) -> tuple[list[Product], str | None]:
    """Liquid and granular Flowers, Fruits & Roots are the same job — keep one."""
    ids = {p.id for p in products}
    if _FFR_LIQUID in ids and _FFR_GRANULAR in ids:
        return [p for p in products if p.id != _FFR_GRANULAR], (
            "Flowers, Fruits & Roots is either the liquid or the granules — not both. "
            "This plan uses the liquid so it can alternate with Activ8."
        )
    return products, None


def program_products_from_catalog(
    rec,
    catalog_products: list[Product],
    *,
    wants_lime: bool = False,
    lawn: bool = True,
    flowering: bool = False,
    deep_green: bool = False,
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
    pro_pack_complete = all(sku in seen for sku in LAWN_LOVERS_PRO_SKUS)
    if champ or (lawn and pro_pack_complete):
        add(by_id.get("886"))
        notes.append(
            "Champion Fairway is on the calendar as the granular lawn fertiliser. Swap to Greens Grade if you keep a low-cut surface."
        )
        if "892" in seen and "886" in seen:
            products = [p for p in products if p.id != "892"]
            seen.discard("892")

    if not lawn:
        if flowering and _FFR_LIQUID not in seen:
            add(by_id.get(_FFR_LIQUID))
        has_ffr = _FFR_LIQUID in seen or _FFR_GRANULAR in seen
        has_a8 = any(sku in seen for sku in _ACTIV8)
        if has_ffr and not has_a8:
            add(by_id.get("A8M") or by_id.get("A8X"))
        if rec.intent == "performance_mode":
            add(by_id.get(_RSL_GRANULAR))
            if _RSL_GRANULAR in seen:
                notes.append(
                    "Roots, Shoots & Leaves granules are the slow-release garden fertiliser — about every 3 months."
                )

    if lawn and deep_green:
        has_iron = any(p.is_iron_based or p.id == "LEN" for p in products)
        if not has_iron:
            add(by_id.get("LIR"))

    # The same-week stack cannot mix lime and iron. A year calendar can: lime first, iron later.
    if wants_lime and not any(p.is_lime_based for p in products):
        add(by_id.get("LIMEGr"))
        notes.append("Lime is first. Wait 6 weeks before iron so pH can move.")

    products, ffr_note = prefer_single_ffr(products)
    if ffr_note:
        notes.append(ffr_note)

    return products, notes


def _first_ok(
    start: date,
    interval: Interval,
    product: Product,
    *,
    fungal: bool,
    region: Region,
    until: date | None = None,
) -> date | None:
    day = start
    stop = until or (start + timedelta(days=366))
    while day < stop:
        if _date_allowed(day, interval, product, fungal=fungal, region=region):
            return day
        day += timedelta(days=1)
    return None


def _date_allowed(
    day: date,
    interval: Interval,
    product: Product,
    *,
    fungal: bool,
    region: Region,
) -> bool:
    if interval.window == "growing_season" and not in_growing_season(day, region):
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


def _liquid_feed_pair(skus: set[str]) -> tuple[str, str] | None:
    """FFR liquid + Activ8Mate or Extra — alternate these, never tank-mix them."""
    if _FFR_LIQUID not in skus:
        return None
    for sku in _ACTIV8:
        if sku in skus:
            return _FFR_LIQUID, sku
    return None


def _replace_sku_dates(
    events: list[dict[str, Any]],
    sku: str,
    dates: list[date],
) -> list[dict[str, Any]]:
    template = next((e for e in events if e["sku"] == sku), None)
    rest = [e for e in events if e["sku"] != sku]
    if template is None:
        return events
    return rest + [{**template, "date": d.isoformat()} for d in dates]


def _alternate_ffr_activ8(
    events: list[dict[str, Any]],
    products: list[Product],
    interval_for: dict[str, Interval],
    *,
    start: date,
    fungal: bool,
    region: Region,
    pair: tuple[str, str],
) -> list[dict[str, Any]]:
    ffr_sku, a8_sku = pair
    by_id = {p.id: p for p in products}
    ffr_p = by_id.get(ffr_sku)
    a8_p = by_id.get(a8_sku)
    if ffr_p is None or a8_p is None:
        return events
    slots = _place_dates(
        start, interval_for[a8_sku], a8_p, fungal=fungal, region=region, offset=0
    )
    ffr_dates: list[date] = []
    a8_dates: list[date] = []
    want_ffr = True
    for slot in slots:
        if want_ffr and _date_allowed(
            slot, interval_for[ffr_sku], ffr_p, fungal=fungal, region=region
        ):
            ffr_dates.append(slot)
            want_ffr = False
        else:
            a8_dates.append(slot)
            want_ffr = True
    events = _replace_sku_dates(events, ffr_sku, ffr_dates)
    events = _replace_sku_dates(events, a8_sku, a8_dates)
    return events


def _snap_to_dates(d: date, anchors: list[date]) -> date:
    nearby = [a for a in anchors if abs((a - d).days) <= MIX_SNAP_DAYS]
    if nearby:
        return min(nearby, key=lambda a: (abs((a - d).days), a))
    later = [a for a in anchors if a >= d]
    if later:
        return later[0]
    return anchors[-1]


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


def _step_after(last: date, interval: Interval, region: Region) -> int:
    """Normal cadence, doubled in winter for frequent year-round sprays."""
    base = interval.cadence_days
    if base <= 0:
        return 14
    if interval.window != "year_round" or interval.one_off or base > 42:
        return base
    nxt = last + timedelta(days=base)
    if in_winter(nxt, region):
        return base * 2
    return base


def _how_often_label(interval: Interval, region: Region) -> str:
    text = interval.how_often
    if not region.winter_months:
        return text
    if interval.window == "year_round" and not interval.one_off and 0 < interval.cadence_days <= 42:
        if interval.cadence_days <= 16:
            return text.rstrip(".") + " · once a month when nights are below 10°C"
        return text.rstrip(".") + " · less often when nights are below 10°C"
    return text


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
    region: Region,
    offset: int,
) -> list[date]:
    end = _calendar_end(start)
    first = _first_ok(
        start + timedelta(days=offset),
        interval,
        product,
        fungal=fungal,
        region=region,
        until=end,
    )
    if first is None:
        return []
    if interval.one_off or interval.cadence_days <= 0 or interval.max_per_year <= 1:
        return [first]

    out = [first]
    last = first
    while len(out) < _PLACE_CAP:
        day = last + timedelta(days=_step_after(last, interval, region))
        if day >= end:
            break
        if _date_allowed(day, interval, product, fungal=fungal, region=region):
            out.append(day)
            last = day
            continue
        # Skip closed windows (winter / fungal summer) and resume when allowed.
        resumed = _first_ok(day, interval, product, fungal=fungal, region=region, until=end)
        if resumed is None or resumed >= end:
            break
        last = resumed
        out.append(resumed)
    return out


def _coalesce_tank_mix(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Put mix-as-concentrate sprays on the same visit as the main spray cadence."""
    mix = [e for e in events if e.get("tank_mix")]
    rest = [e for e in events if not e.get("tank_mix")]
    if len({e["sku"] for e in mix}) < 2:
        return events

    pair = _liquid_feed_pair({e["sku"] for e in mix})
    if pair:
        feed_skus = {pair[0], pair[1]}
        feeds = [e for e in mix if e["sku"] in feed_skus]
        companions = [e for e in mix if e["sku"] not in feed_skus]
        anchors = sorted({date.fromisoformat(e["date"]) for e in feeds})
        if not companions or not anchors:
            return rest + feeds + companions
        snapped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for ev in companions:
            target = _snap_to_dates(date.fromisoformat(ev["date"]), anchors).isoformat()
            key = (ev["sku"], target)
            if key in seen:
                continue
            seen.add(key)
            snapped.append({**ev, "date": target})
        return rest + feeds + snapped

    sku_counts: dict[str, int] = {}
    for e in mix:
        sku_counts[e["sku"]] = sku_counts.get(e["sku"], 0) + 1
    anchor_sku = max(sku_counts, key=lambda s: sku_counts[s])
    anchors = sorted({date.fromisoformat(e["date"]) for e in mix if e["sku"] == anchor_sku})
    if not anchors:
        return events

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ev in mix:
        target = _snap_to_dates(date.fromisoformat(ev["date"]), anchors).isoformat()
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
    weed_suppression: bool = False,
    region: str | Region | None = None,
    extra_notes: list[str] | None = None,
    choice_summary: list[str] | None = None,
) -> dict[str, Any]:
    loc = region if isinstance(region, Region) else parse_region(region)
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
        dates = _place_dates(
            start, interval, product, fungal=fungal, region=loc, offset=offset
        )
        rate = rates.for_sku(product.id, lawn=lawn, area_m2=area_m2)
        rate_label = (rate.per_100m2 if rate else "") or ""
        amount_label = (rate.for_area if rate else None)
        url = product.product_url or (rate.product_url if rate else None)
        how_often = _how_often_label(interval, loc)
        card = _product_dict(product)
        card.update(
            {
                "how_often": how_often,
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
                    "how_often": how_often,
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

    pair = _liquid_feed_pair({p.id for p in products})
    if pair:
        events = _alternate_ffr_activ8(
            events,
            products,
            interval_for,
            start=start,
            fungal=fungal,
            region=loc,
            pair=pair,
        )
        ffr_how = "Every 4 weeks during flowering/fruiting, alternating with Activ8"
        a8_how = "Every 4 weeks, alternating with Flowers, Fruits & Roots"
        if loc.winter_months:
            a8_how += " · once a month when nights are below 10°C"
        for card in product_cards:
            if card["id"] == pair[0]:
                card["how_often"] = ffr_how
            elif card["id"] == pair[1]:
                card["how_often"] = a8_how
        for ev in events:
            if ev["sku"] == pair[0]:
                ev["how_often"] = ffr_how
            elif ev["sku"] == pair[1]:
                ev["how_often"] = a8_how

    events = _coalesce_tank_mix(events)
    events = _resolve_same_day(events)
    counts: dict[str, int] = {}
    for ev in events:
        counts[ev["sku"]] = counts.get(ev["sku"], 0) + 1
    for card in product_cards:
        card["applications"] = counts.get(card["id"], 0)

    all_notes = [
        n for n in (extra_notes or []) if n and not _is_iron_spacing_note(n)
    ] + place_warnings(products, lawn=lawn)
    if not lawn:
        all_notes.append(
            "For natives and other sensitive plants, use Seaweed Secrets and Activ8Mate at half strength."
        )
    if fungal:
        all_notes.append(
            "This plan does not include chemical fungicides. We support plant and soil health so lawns and gardens can resist disease, and we ease high-nitrogen feeds in summer."
        )
    if weed_suppression:
        all_notes.append(WEED_SUPPRESSION_NOTE)
    if any(p.id == "513" for p in products):
        all_notes.append(
            "Spread Humate granules on the top layer of soil, under mulch, or dug in. They do not need to be watered in."
        )
    if any(
        interval_for[p.id].window == "year_round"
        and not interval_for[p.id].one_off
        and interval_for[p.id].cadence_days <= 42
        for p in products
    ):
        all_notes.append(loc.winter_note)
    if pair:
        a8_label = "Activ8EXTRA" if pair[1] == "A8X" else "Activ8Mate"
        all_notes.append(
            f"Alternate between Flowers, Fruits & Roots and {a8_label} each feed. "
            "FFR is for flowering/fruiting; Activ8 is the regular feed. Do not mix those two in the same sprayer."
        )
    mix_entries: list[tuple[str, str]] = []
    seen_mix: set[str] = set()
    for ev in events:
        if ev.get("tank_mix") and ev["sku"] not in seen_mix:
            seen_mix.add(ev["sku"])
            mix_entries.append((ev["sku"], _note_name(ev["sku"], ev["name"])))
    pair_skus = {pair[0], pair[1]} if pair else set()
    mix_names = [name for sku, name in mix_entries if sku not in pair_skus]
    if pair and mix_names:
        all_notes.append(
            "On each feed day, mix "
            + _join_names(mix_names)
            + " with that day's feed. Jar test if it is a new combination."
        )
    elif not pair and len(mix_names) >= 2:
        all_notes.append(
            "Mix these as concentrates in one sprayer on the same day: "
            + _join_names(mix_names)
            + ". Do not add iron to that tank."
        )
    if any(e["tank_group"] == "iron" for e in events) and any(e.get("blocks_iron") for e in events):
        all_notes.append(
            "Liquid iron is on a different day from seaweed, humic, wetter, and Activ8. Do not mix them in the same sprayer."
        )

    return {
        "region": loc.id,
        "climate": loc.id,
        "climate_label": loc.label,
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

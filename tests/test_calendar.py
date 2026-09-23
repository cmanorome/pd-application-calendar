from datetime import date

from app import _calendar_payload


def _lawn_payload(**extra):
    body = {
        "recommendation_mode": "goals",
        "use_case": "lawn",
        "intent": "maintenance_mode",
        "start_date": "2026-09-17",
        "area_m2": 100,
        "goal_weights": {"thickening_and_density": 1.0},
        "confidence_level": "somewhat_sure",
    }
    body.update(extra)
    return body


def test_lawn_calendar_has_events():
    plan = _calendar_payload(_lawn_payload())
    assert plan["events"], "expected dated events"
    assert plan["products"], "expected products on the plan"
    assert plan["ics"].startswith("BEGIN:VCALENDAR")
    skus = {e["sku"] for e in plan["events"]}
    assert "SWS" in skus or any(p["role_type"] == "biology" for p in plan["products"])
    assert "half strength" not in " ".join(plan["notes"]).lower()


def test_iron_not_same_day_as_seaweed():
    plan = _calendar_payload(
        _lawn_payload(
            recommendation_mode="problems",
            yellowing=True,
            patchy_lawn=True,
        )
    )
    by_date = {}
    for ev in plan["events"]:
        by_date.setdefault(ev["date"], []).append(ev)
    for day, group in by_date.items():
        iron = [e for e in group if e["tank_group"] == "iron"]
        blocked = [e for e in group if e.get("blocks_iron")]
        assert not (iron and blocked), f"iron shares {day} with {blocked}"


def test_lime_before_iron():
    plan = _calendar_payload(
        _lawn_payload(
            recommendation_mode="problems",
            yellowing=True,
            acidic=True,
        )
    )
    lime_dates = [e["date"] for e in plan["events"] if e["sku"] in {"LIMEGr", "DOL"}]
    iron_dates = [e["date"] for e in plan["events"] if e["tank_group"] == "iron"]
    if lime_dates and iron_dates:
        first_lime = date.fromisoformat(min(lime_dates))
        first_iron = date.fromisoformat(min(iron_dates))
        assert (first_iron - first_lime).days >= 42


def test_garden_uses_garden_products():
    plan = _calendar_payload(
        {
            "recommendation_mode": "goals",
            "use_case": "garden_beds",
            "intent": "maintenance_mode",
            "start_date": "2026-09-17",
            "goal_weights": {"strong_flowering_and_fruiting": 1.0},
        }
    )
    names = " ".join(p["name"].lower() for p in plan["products"])
    assert "champion" not in names
    assert plan["events"]
    skus = {p["id"] for p in plan["products"]}
    assert "721" in skus
    assert "A8M" in skus or "A8X" in skus
    blob = " ".join(plan["notes"]).lower()
    assert "native" in blob
    assert "half strength" in blob
    assert "seaweed secrets" in blob
    assert "activ8mate" in blob


def test_garden_ffr_alternates_with_activ8():
    plan = _calendar_payload(
        {
            "recommendation_mode": "goals",
            "use_case": "garden_beds",
            "intent": "maintenance_mode",
            "start_date": "2026-09-17",
            "goal_weights": {"strong_flowering_and_fruiting": 1.0},
        }
    )
    skus = {p["id"] for p in plan["products"]}
    assert "721" in skus
    a8 = "A8M" if "A8M" in skus else "A8X"
    assert a8 in skus
    ffr_dates = {e["date"] for e in plan["events"] if e["sku"] == "721"}
    a8_dates = {e["date"] for e in plan["events"] if e["sku"] == a8}
    assert ffr_dates
    assert a8_dates
    assert not (ffr_dates & a8_dates), "FFR and Activ8 should alternate, not share a spray day"
    growing = sorted(
        date.fromisoformat(d)
        for d in (ffr_dates | a8_dates)
        if d[5:7] in {"09", "10", "11", "12", "01", "02", "03", "04"}
    )
    for a, b in zip(growing, growing[1:]):
        gap = (b - a).days
        if gap > 40:
            continue
        assert 10 <= gap <= 18, f"garden feeds should stay about fortnightly: {a} -> {b}"
    note = " ".join(plan["notes"]).lower()
    assert "alternate" in note
    card = next(p for p in plan["products"] if p["id"] == "721")
    assert "flowering/fruiting" in card["how_often"]
    assert "active growth" not in card["how_often"]
    a8_card = next(p for p in plan["products"] if p["id"] == a8)
    assert "alternating" in a8_card["how_often"].lower()


def test_garden_does_not_use_both_ffr_forms():
    plan = _calendar_payload(
        {
            "recommendation_mode": "goals",
            "use_case": "garden_beds",
            "intent": "maintenance_mode",
            "start_date": "2026-09-17",
            "goal_weights": {
                "strong_flowering_and_fruiting": 1.0,
                "improved_soil_fertility": 1.0,
                "root_development_transplant": 1.0,
            },
        }
    )
    ids = [p["id"] for p in plan["products"]]
    assert "721" in ids
    assert "575" not in ids

    picked = _calendar_payload(
        {
            "path": "pick",
            "use_case": "garden_beds",
            "start_date": "2026-09-17",
            "skus": ["575", "721", "A8M"],
        }
    )
    picked_ids = [p["id"] for p in picked["products"]]
    assert "721" in picked_ids
    assert "575" not in picked_ids
    assert any("not both" in n.lower() for n in picked["notes"])


def test_garden_max_results_includes_rsl_granular():
    keep = _calendar_payload(
        {
            "recommendation_mode": "goals",
            "use_case": "garden_beds",
            "intent": "maintenance_mode",
            "start_date": "2026-09-17",
            "goal_weights": {"strong_flowering_and_fruiting": 1.0},
        }
    )
    assert "1156" not in {p["id"] for p in keep["products"]}

    plan = _calendar_payload(
        {
            "recommendation_mode": "goals",
            "use_case": "garden_beds",
            "intent": "performance_mode",
            "start_date": "2026-09-17",
            "goal_weights": {"strong_flowering_and_fruiting": 1.0},
        }
    )
    ids = [p["id"] for p in plan["products"]]
    assert "1156" in ids
    assert "721" in ids
    assert "575" not in ids
    assert "A8M" in ids or "A8X" in ids
    card = next(p for p in plan["products"] if p["id"] == "1156")
    assert "3 months" in card["how_often"].lower() or "90" in card["how_often"]
    dates = sorted(date.fromisoformat(e["date"]) for e in plan["events"] if e["sku"] == "1156")
    assert dates
    for a, b in zip(dates, dates[1:]):
        assert 80 <= (b - a).days <= 100, f"RSL gap should be ~3 months: {a} -> {b}"
    assert any("Roots, Shoots & Leaves" in n for n in plan["notes"])


def test_picked_ffr_and_activ8_alternate():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "garden_beds",
            "start_date": "2026-09-17",
            "skus": ["721", "A8M", "SWS"],
        }
    )
    ffr_dates = {e["date"] for e in plan["events"] if e["sku"] == "721"}
    a8_dates = {e["date"] for e in plan["events"] if e["sku"] == "A8M"}
    assert ffr_dates and a8_dates
    assert not (ffr_dates & a8_dates)
    sws_dates = {e["date"] for e in plan["events"] if e["sku"] == "SWS"}
    assert ffr_dates <= sws_dates
    assert a8_dates <= sws_dates
    assert "alternate" in " ".join(plan["notes"]).lower()


def test_picked_products_only_those_skus():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "lawn",
            "start_date": "2026-09-17",
            "area_m2": 100,
            "skus": ["SWS", "886", "LIR"],
        }
    )
    assert plan.get("error") is None
    assert {p["id"] for p in plan["products"]} == {"SWS", "886", "LIR"}
    by_date = {}
    for ev in plan["events"]:
        by_date.setdefault(ev["date"], []).append(ev)
    for day, group in by_date.items():
        iron = [e for e in group if e["tank_group"] == "iron"]
        blocked = [e for e in group if e.get("blocks_iron")]
        assert not (iron and blocked), f"iron shares {day} with {blocked}"


def test_pick_requires_a_product():
    plan = _calendar_payload({"path": "pick", "use_case": "lawn", "start_date": "2026-09-17"})
    assert plan.get("error")


def test_lawn_picker_includes_uptake_products():
    from app import catalog_payload

    lawn = {p["id"]: p["fit"] for p in catalog_payload("lawn")["products"]}
    garden = {p["id"]: p["fit"] for p in catalog_payload("garden_beds")["products"]}
    for sku in ("STM", "29800", "414", "513", "SWS"):
        assert lawn[sku], f"{sku} should be a core lawn pick"
        assert garden[sku], f"{sku} should be a core garden pick"
    assert lawn["886"]
    assert not garden["886"]
    assert garden["721"]
    assert not lawn["721"]


def test_usage_guide_dots():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "lawn",
            "start_date": "2026-09-17",
            "skus": ["SWS", "STM", "LIR", "LEN", "886", "557"],
        }
    )
    usage = {p["id"]: p.get("usage") or {} for p in plan["products"]}
    assert usage["SWS"]["mix_together"]
    assert usage["STM"]["mix_together"]
    assert usage["STM"]["hydroponic"]
    assert usage["LIR"]["independent"]
    assert not usage["LIR"]["mix_together"]
    assert usage["LEN"]["independent"]
    assert usage["LEN"]["hose_on"]
    assert usage["886"]["water_in"]
    assert usage["886"]["independent"]
    assert not any(usage["557"].get(k) for k in (
        "mix_together", "independent", "water_in", "soil_drench",
        "foliar", "fertigation", "hydroponic", "hose_on", "mix_with_iron",
    ))
    assert not next(p.get("usage_labels") for p in plan["products"] if p["id"] == "557")
    len_events = [e for e in plan["events"] if e["sku"] == "LEN"]
    sws_dates = {e["date"] for e in plan["events"] if e["sku"] == "SWS"}
    assert len_events
    assert all(e["tank_group"] == "iron" for e in len_events)
    assert not any(e["date"] in sws_dates for e in len_events)


def test_mixable_concentrates_share_spray_days():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "lawn",
            "start_date": "2026-09-17",
            "area_m2": 100,
            "skus": ["SWS", "A8X", "STM", "29800", "NSWL", "LIR"],
        }
    )
    mix = [e for e in plan["events"] if e.get("tank_mix")]
    iron = [e for e in plan["events"] if e["tank_group"] == "iron"]
    assert {e["sku"] for e in mix} >= {"SWS", "A8X", "STM", "29800", "NSWL"}
    first = {}
    for e in mix:
        first.setdefault(e["sku"], e["date"])
    assert first["SWS"] == first["A8X"] == first["STM"] == first["29800"] == first["NSWL"]
    mix_dates = {e["date"] for e in mix}
    assert not any(e["date"] in mix_dates for e in iron)
    first_iron = min(e["date"] for e in iron)
    assert (date.fromisoformat(first_iron) - date.fromisoformat(first["SWS"])).days >= 3
    sws_dates = {e["date"] for e in mix if e["sku"] == "SWS"}
    for sku in ("A8X", "STM", "29800", "NSWL"):
        sku_dates = {e["date"] for e in mix if e["sku"] == sku}
        assert sku_dates
        assert sku_dates <= sws_dates, f"{sku} sprayed on extra days {sku_dates - sws_dates}"


def test_usage_guide_export_joins_on_sku():
    import csv
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    rows = list(csv.DictReader((root / "data" / "product_usage_guide.csv").open(encoding="utf-8-sig")))
    by_sku = {r["sku"]: r for r in rows}
    assert by_sku["STM"]["mix_with_iron"] == "1"
    assert by_sku["SWS"]["mix_together"] == "1"
    assert by_sku["LIR"]["independent"] == "1"
    assert by_sku["557"]["mix_together"] == "0"
    assert by_sku["557"]["independent"] == "0"
    assert by_sku["557"]["water_in"] == "0"
    assert by_sku["513"]["water_in"] == "0"
    assert "top layer of soil" in by_sku["513"]["application_notes"]
    assert by_sku["557"]["soil_drench"] == "0"
    assert by_sku["557"]["foliar"] == "0"
    assert by_sku["557"]["fertigation"] == "0"
    assert by_sku["NSO"]["in_catalog"] == "0"
    rate_rows = list(csv.DictReader((root / "data" / "product_usage_guide_rates.csv").open(encoding="utf-8-sig")))
    assert any(r["sku"] == "STM" and "3 mL" in r["amount_text"] for r in rate_rows)


def test_master_application_guide_joins_sources():
    import csv
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    products = list(csv.DictReader((root / "data" / "pd_master_products.csv").open(encoding="utf-8-sig")))
    by_sku = {r["sku"].upper(): r for r in products}
    assert by_sku["513"]["water_in"] == "0"
    assert "top layer of soil" in by_sku["513"]["combined_notes"].lower()
    assert by_sku["557"]["mix_together"] == "0"
    assert by_sku["557"]["water_in"] == "0"
    assert by_sku["SWS"]["garden_natives_half_strength"] == "1"
    assert by_sku["A8M"]["garden_natives_half_strength"] == "1"
    assert by_sku["A8X"]["garden_natives_half_strength"] == "0"
    assert by_sku["STM"]["calculator_rate_100m2"]
    notes = list(csv.DictReader((root / "data" / "pd_master_program_notes.csv").open(encoding="utf-8-sig")))
    ids = {r["note_id"] for r in notes}
    assert "garden_natives_half_strength" in ids
    assert "fungal_no_chemical_fungicides" in ids
    assert "weed_suppression_no_chemicals" in ids
    assert "winter_nights_below_10c" in ids
    assert "winter_east_coast_june_july" in ids
    assert "winter_north_usual_cadence" in ids
    assert (root / "data" / "pd_master_application_guide.xlsx").is_file()


def test_year_round_fills_twelfth_month():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "lawn",
            "start_date": "2026-09-01",
            "area_m2": 100,
            "skus": ["SWS", "STM", "A8X"],
        }
    )
    august = [e for e in plan["events"] if e["date"].startswith("2027-08")]
    assert any(e["sku"] == "SWS" for e in august), "year-round seaweed should still run in August"
    assert any(e["sku"] == "STM" for e in august)
    assert any(e["sku"] == "A8X" for e in august), "Activ8EXTRA should still run monthly in August"
    assert max(e["date"] for e in plan["events"] if e["sku"] == "SWS") < "2027-09-01"


def test_winter_eases_year_round_cadence():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "lawn",
            "start_date": "2026-09-01",
            "skus": ["SWS", "STM", "A8X"],
        }
    )
    winter = sorted(
        date.fromisoformat(e["date"])
        for e in plan["events"]
        if e["sku"] == "SWS" and e["date"][5:7] in {"06", "07", "08"}
    )
    growing = [
        date.fromisoformat(e["date"])
        for e in plan["events"]
        if e["sku"] == "SWS" and e["date"][5:7] in {"09", "10", "11", "12", "01", "02", "03", "04"}
    ]
    assert winter, "year-round products should still apply in winter, just less often"
    for a, b in zip(winter, winter[1:]):
        assert (b - a).days >= 21, f"winter gap too tight: {a} -> {b}"
    assert len(winter) < len(growing) / 2
    a8x_winter = sorted(
        date.fromisoformat(e["date"])
        for e in plan["events"]
        if e["sku"] == "A8X" and e["date"][5:7] in {"06", "07", "08"}
    )
    assert a8x_winter, "Activ8EXTRA should keep going in winter, about monthly"
    for a, b in zip(a8x_winter, a8x_winter[1:]):
        assert (b - a).days >= 21, f"A8X winter gap too tight: {a} -> {b}"
    winter_note = " ".join(plan["notes"])
    assert "10°C" in winter_note or "10°c" in winter_note.lower()
    assert "pause until spring" not in winter_note.lower()


def test_blank_region_uses_southern_winter():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "lawn",
            "start_date": "2026-09-01",
            "skus": ["SWS"],
        }
    )
    assert plan["region"] == "south"
    assert "Southern" in plan["climate_label"]


def test_north_keeps_usual_year_round_cadence():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "lawn",
            "start_date": "2026-09-01",
            "region": "north",
            "skus": ["SWS", "A8X"],
        }
    )
    assert plan["region"] == "north"
    cool = sorted(
        date.fromisoformat(e["date"])
        for e in plan["events"]
        if e["sku"] == "SWS" and e["date"][5:7] in {"06", "07", "08"}
    )
    assert len(cool) >= 5
    for a, b in zip(cool, cool[1:]):
        assert (b - a).days <= 16, f"north winter should stay fortnightly: {a} -> {b}"
    card = next(p for p in plan["products"] if p["id"] == "SWS")
    assert "once a month when nights" not in card["how_often"]
    notes = " ".join(plan["notes"]).lower()
    assert "usual cadence" in notes
    assert "june to august" not in notes


def test_east_coast_winter_is_shorter_than_south():
    body = {
        "path": "pick",
        "use_case": "lawn",
        "start_date": "2026-09-01",
        "skus": ["SWS"],
    }
    south = _calendar_payload(body)
    east = _calendar_payload({**body, "region": "east_coast"})
    assert east["region"] == "east_coast"
    jun_jul = sorted(
        date.fromisoformat(e["date"])
        for e in east["events"]
        if e["sku"] == "SWS" and e["date"][5:7] in {"06", "07"}
    )
    assert jun_jul
    for a, b in zip(jun_jul, jun_jul[1:]):
        assert (b - a).days >= 21, f"east-coast Jun–Jul should ease: {a} -> {b}"
    south_aug = [e for e in south["events"] if e["sku"] == "SWS" and e["date"].startswith("2027-08")]
    east_aug = [e for e in east["events"] if e["sku"] == "SWS" and e["date"].startswith("2027-08")]
    assert len(east_aug) > len(south_aug)
    notes = " ".join(east["notes"]).lower()
    assert "june and july" in notes


def test_north_growing_season_products_run_in_june():
    body = {
        "path": "pick",
        "use_case": "lawn",
        "start_date": "2026-09-01",
        "skus": ["LIR"],
    }
    south = _calendar_payload(body)
    north = _calendar_payload({**body, "region": "north"})
    south_june = [e for e in south["events"] if e["sku"] == "LIR" and e["date"][5:7] == "06"]
    north_june = [e for e in north["events"] if e["sku"] == "LIR" and e["date"][5:7] == "06"]
    assert not south_june
    assert north_june


def test_fert_granules_every_three_months():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "lawn",
            "start_date": "2026-09-01",
            "skus": ["886"],
        }
    )
    dates = sorted(date.fromisoformat(e["date"]) for e in plan["events"] if e["sku"] == "886")
    assert dates
    for a, b in zip(dates, dates[1:]):
        assert 80 <= (b - a).days <= 100, f"Champion gap should be ~3 months: {a} -> {b}"
    assert any(d.month in {6, 7, 8} for d in dates), "granular fertiliser should still land in winter"
    card = next(p for p in plan["products"] if p["id"] == "886")
    assert "Every 3 months" in card["how_often"]


def test_lawn_deep_green_includes_iron():
    plan = _calendar_payload(
        {
            "recommendation_mode": "goals",
            "use_case": "lawn",
            "intent": "maintenance_mode",
            "start_date": "2026-09-17",
            "goal_weights": {"deep_green_colour": 1.0},
        }
    )
    skus = {p["id"] for p in plan["products"]}
    assert "LIR" in skus or "LEN" in skus or "547" in skus or "846" in skus, skus
    density = _calendar_payload(
        {
            "recommendation_mode": "goals",
            "use_case": "lawn",
            "intent": "maintenance_mode",
            "start_date": "2026-09-17",
            "goal_weights": {"thickening_and_density": 1.0},
        }
    )
    density_skus = {p["id"] for p in density["products"]}
    assert "LIR" not in density_skus


def test_humate_granules_not_watered_in():
    plan = _calendar_payload(
        {
            "path": "pick",
            "use_case": "garden_beds",
            "start_date": "2026-09-17",
            "skus": ["513"],
        }
    )
    card = next(p for p in plan["products"] if p["id"] == "513")
    assert not (card.get("usage") or {}).get("water_in")
    assert "Water in" not in (card.get("usage_labels") or [])
    notes = " ".join(plan["notes"]).lower()
    assert "top layer of soil" in notes
    assert "do not need to be watered in" in notes
    event = next(e for e in plan["events"] if e["sku"] == "513")
    assert "does not need to be watered in" in (event.get("notes") or "").lower()


def test_fungal_issues_note_explains_no_fungicides():
    plan = _calendar_payload(
        _lawn_payload(recommendation_mode="problems", fungal_issues=True)
    )
    blob = " ".join(plan["notes"]).lower()
    assert "chemical fungicides" in blob
    assert "high-nitrogen" in blob
    healthy = _calendar_payload(_lawn_payload())
    assert "fungicide" not in " ".join(healthy["notes"]).lower()


def test_weed_suppression_note_explains_no_chemicals():
    plan = _calendar_payload(
        _lawn_payload(goal_weights={"weed_suppression_through_dominance": 1.0})
    )
    blob = " ".join(plan["notes"]).lower()
    assert "chemical weed killers" in blob
    assert "plantdoctor.com.au/weed-and-pest-control" in blob
    healthy = _calendar_payload(_lawn_payload())
    assert "weed killer" not in " ".join(healthy["notes"]).lower()


def test_plan_notes_are_tidy():
    plan = _calendar_payload(
        _lawn_payload(goal_weights={"deep_green_colour": 1.0, "thickening_and_density": 1.0})
    )
    notes = plan["notes"]
    iron_notes = [n for n in notes if "different day" in n.lower() and "iron" in n.lower()]
    assert len(iron_notes) == 1, notes
    blob = " ".join(notes)
    assert "Boosted Liquid Fertiliser" not in blob
    assert "Concentrated Liquid Seaweed" not in blob
    assert "Super Concentrate Bio-Stimulant" not in blob
    mix = next((n for n in notes if n.startswith("Mix these")), "")
    assert mix
    assert "Activ8EXTRA" in mix
    assert "Seaweed Secrets" in mix
    assert "Stimulizer" in mix


def test_nutrient_lockout_leads_with_fulvic():
    lawn = _calendar_payload(
        {
            "recommendation_mode": "problems",
            "use_case": "lawn",
            "nutrient_lockout": True,
            "start_date": "2026-09-21",
        }
    )
    lawn_ids = [p["id"] for p in lawn["products"]]
    assert "414" in lawn_ids
    assert lawn_ids[0] == "414"
    garden = _calendar_payload(
        {
            "recommendation_mode": "problems",
            "use_case": "garden_beds",
            "nutrient_lockout": True,
            "start_date": "2026-09-21",
        }
    )
    garden_ids = [p["id"] for p in garden["products"]]
    assert garden_ids[0] == "414"


def test_majority_lawn_goals_use_full_pro_pack():
    few = _calendar_payload(_lawn_payload())
    few_ids = [p["id"] for p in few["products"]]
    assert "STM" in few_ids
    assert "29800" not in few_ids

    majority = _calendar_payload(
        _lawn_payload(
            goal_weights={
                "deep_green_colour": 1.0,
                "thickening_and_density": 1.0,
                "fast_recovery_from_stress": 1.0,
            }
        )
    )
    majority_ids = [p["id"] for p in majority["products"]]
    for sku in ("SWS", "A8X", "29800", "LIR", "STM", "886"):
        assert sku in majority_ids, majority_ids
    assert majority_ids[:5] == ["SWS", "A8X", "29800", "LIR", "STM"]
    assert any("Lawn Lovers Pro Pack" in n for n in majority["notes"])
    assert any("Champion" in n for n in majority["notes"])


def test_majority_lawn_adds_soil_specific_products():
    wet = _calendar_payload(
        _lawn_payload(
            hydrophobic=True,
            goal_weights={
                "deep_green_colour": 1.0,
                "thickening_and_density": 1.0,
                "fast_recovery_from_stress": 1.0,
            },
        )
    )
    wet_ids = [p["id"] for p in wet["products"]]
    for sku in ("SWS", "A8X", "29800", "LIR", "STM", "886"):
        assert sku in wet_ids, wet_ids
    assert "NSWL" in wet_ids or "664" in wet_ids, wet_ids

    lime = _calendar_payload(
        _lawn_payload(
            acidic=True,
            goal_weights={
                "deep_green_colour": 1.0,
                "thickening_and_density": 1.0,
                "fast_recovery_from_stress": 1.0,
            },
        )
    )
    lime_ids = [p["id"] for p in lime["products"]]
    assert "LIMEGr" in lime_ids or "DOL" in lime_ids, lime_ids
    for sku in ("SWS", "A8X", "29800", "LIR", "STM", "886"):
        assert sku in lime_ids, lime_ids


def test_majority_garden_goals_prefer_quantum_h():
    plan = _calendar_payload(
        {
            "recommendation_mode": "goals",
            "use_case": "garden_beds",
            "intent": "maintenance_mode",
            "start_date": "2026-09-17",
            "goal_weights": {
                "improved_soil_fertility": 1.0,
                "root_development_transplant": 1.0,
                "consistent_growth_across_seasons": 1.0,
            },
            "confidence_level": "somewhat_sure",
        }
    )
    ids = [p["id"] for p in plan["products"]]
    assert "29800" in ids


if __name__ == "__main__":
    test_lawn_calendar_has_events()
    test_iron_not_same_day_as_seaweed()
    test_lime_before_iron()
    test_garden_uses_garden_products()
    test_garden_ffr_alternates_with_activ8()
    test_garden_does_not_use_both_ffr_forms()
    test_garden_max_results_includes_rsl_granular()
    test_picked_ffr_and_activ8_alternate()
    test_picked_products_only_those_skus()
    test_pick_requires_a_product()
    test_lawn_picker_includes_uptake_products()
    test_usage_guide_dots()
    test_mixable_concentrates_share_spray_days()
    test_usage_guide_export_joins_on_sku()
    test_master_application_guide_joins_sources()
    test_year_round_fills_twelfth_month()
    test_winter_eases_year_round_cadence()
    test_blank_region_uses_southern_winter()
    test_north_keeps_usual_year_round_cadence()
    test_east_coast_winter_is_shorter_than_south()
    test_north_growing_season_products_run_in_june()
    test_fert_granules_every_three_months()
    test_lawn_deep_green_includes_iron()
    test_humate_granules_not_watered_in()
    test_fungal_issues_note_explains_no_fungicides()
    test_weed_suppression_note_explains_no_chemicals()
    test_plan_notes_are_tidy()
    test_nutrient_lockout_leads_with_fulvic()
    test_majority_lawn_goals_use_full_pro_pack()
    test_majority_lawn_adds_soil_specific_products()
    test_majority_garden_goals_prefer_quantum_h()
    print("ok")

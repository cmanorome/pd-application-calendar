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
            "skus": ["SWS", "STM", "LIR", "LEN", "886"],
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
    assert by_sku["NSO"]["in_catalog"] == "0"
    rate_rows = list(csv.DictReader((root / "data" / "product_usage_guide_rates.csv").open(encoding="utf-8-sig")))
    assert any(r["sku"] == "STM" and "3 mL" in r["amount_text"] for r in rate_rows)


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
    assert not any(e["sku"] == "A8X" for e in august), "Activ8EXTRA is growing-season only"
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
    assert not any(e["sku"] == "A8X" and e["date"][5:7] in {"06", "07", "08"} for e in plan["events"])


if __name__ == "__main__":
    test_lawn_calendar_has_events()
    test_iron_not_same_day_as_seaweed()
    test_lime_before_iron()
    test_garden_uses_garden_products()
    test_picked_products_only_those_skus()
    test_pick_requires_a_product()
    test_lawn_picker_includes_uptake_products()
    test_usage_guide_dots()
    test_mixable_concentrates_share_spray_days()
    test_usage_guide_export_joins_on_sku()
    test_year_round_fills_twelfth_month()
    test_winter_eases_year_round_cadence()
    print("ok")

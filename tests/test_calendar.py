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


if __name__ == "__main__":
    test_lawn_calendar_has_events()
    test_iron_not_same_day_as_seaweed()
    test_lime_before_iron()
    test_garden_uses_garden_products()
    test_picked_products_only_those_skus()
    test_pick_requires_a_product()
    test_lawn_picker_includes_uptake_products()
    print("ok")

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from pd_engine import recommend
from pd_engine.catalog import Catalog
from pd_engine.soil_test import lime_is_appropriate
from pd_engine.types import RoleType
from scheduler import build_calendar, to_ics
from scheduler.build import program_products_from_catalog
from scheduler.intervals import IntervalTable
from scheduler.rates import RateBook


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CATALOG_CSV = DATA / "plant_doctor_recommendation_engine_template.csv"
INTERVALS_CSV = DATA / "schedule_intervals.csv"
RATES_CSV = DATA / "PD-application-rates-sheet.csv"
INDEX_HTML = ROOT / "static" / "index.html"

app = FastAPI(title="Plant Doctor Application Calendar", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_catalog = Catalog.from_csv(CATALOG_CSV)
_intervals = IntervalTable.from_csv(INTERVALS_CSV)
_rates = RateBook.from_csv(RATES_CSV)


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "on", "checked"}


def _goal_selected(form: dict[str, Any], key: str) -> bool:
    if _truthy(form.get(key)):
        return True
    gw = form.get("goal_weights")
    if isinstance(gw, dict):
        return _f01(gw.get(key)) >= 0.35
    return False


def _f01(v: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default


def _season_for(day: date) -> str:
    if day.month in (9, 10, 11):
        return "spring"
    if day.month in (12, 1, 2):
        return "summer"
    if day.month in (3, 4, 5):
        return "autumn"
    return "winter"


def _parse_start(raw: Any) -> date:
    text = str(raw or "").strip()
    if not text:
        return date.today()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def _parse_area(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def to_engine_payload(form: dict[str, Any], start: date) -> dict[str, Any]:
    confidence_label = str(form.get("confidence_level") or "somewhat_sure").strip().lower()
    confidence_map = {"not_sure": 0.45, "somewhat_sure": 0.6, "very_sure": 0.85}
    confidence = confidence_map.get(confidence_label, 0.6)

    problems = {
        "yellowing": 1.0 if _truthy(form.get("yellowing")) else 0.0,
        "slow_growth": 1.0 if _truthy(form.get("slow_growth")) else 0.0,
        "weak_roots": 1.0 if _truthy(form.get("weak_roots")) else 0.0,
        "nutrient_lockout": 1.0 if _truthy(form.get("nutrient_lockout")) else 0.0,
        "patchy_lawn": 1.0 if _truthy(form.get("patchy_lawn")) else 0.0,
        "compaction": 1.0 if _truthy(form.get("compaction")) else 0.0,
        "poor_water_retention": 1.0 if _truthy(form.get("poor_water_retention")) else 0.0,
        "fungal_issues": 1.0 if _truthy(form.get("fungal_issues")) else 0.0,
        "poor_flowering": 1.0 if _truthy(form.get("poor_flowering")) else 0.0,
    }
    soils = {
        "sandy": 1.0 if _truthy(form.get("sandy")) else 0.0,
        "clay": 1.0 if _truthy(form.get("clay")) else 0.0,
        "acidic": 1.0 if _truthy(form.get("acidic")) else 0.0,
        "alkaline": 1.0 if _truthy(form.get("alkaline")) else 0.0,
        "low_organic_matter": 1.0 if _truthy(form.get("low_organic_matter")) else 0.0,
        "hydrophobic": 1.0 if _truthy(form.get("hydrophobic")) else 0.0,
    }
    problems = {k: v for k, v in problems.items() if v > 0}
    soils = {k: v for k, v in soils.items() if v > 0}

    rec_mode = str(form.get("recommendation_mode") or "goals").strip().lower()
    if rec_mode not in ("problems", "goals"):
        rec_mode = "goals"

    intent = str(form.get("intent") or "maintenance_mode").strip().lower()
    if rec_mode == "problems":
        intent = "rescue_mode"
    elif rec_mode == "goals" and intent in ("diagnosis_mode", "rescue_mode"):
        intent = "maintenance_mode"

    uc = str(form.get("use_case") or "lawn").strip().lower()
    if uc not in ("lawn", "garden_beds"):
        uc = "lawn"
    gv = "lawn" if uc == "lawn" else "garden"

    goal_weights: dict[str, float] = {}
    gw = form.get("goal_weights")
    if isinstance(gw, dict):
        for k, v in gw.items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv > 0:
                goal_weights[str(k).strip()] = max(0.0, min(1.0, fv))

    return {
        "intent": intent,
        "season": _season_for(start),
        "use_case": uc,
        "recommendation_mode": rec_mode,
        "goal_vertical": gv,
        "goal_weights": goal_weights,
        "confidence": _f01(form.get("confidence", confidence), confidence),
        "problems": problems,
        "soils": soils,
        "soil_ph": form.get("soil_ph") or None,
        "soil_ph_method": form.get("soil_ph_method") or "water",
        "organic_matter_pct": form.get("organic_matter_pct") or None,
    }


def _short_name(name: str) -> str:
    text = (name or "").strip()
    if "(" in text:
        text = text.split("(")[0].strip()
    return text or "Product"


def _use_case(form: dict[str, Any]) -> str:
    uc = str(form.get("use_case") or "lawn").strip().lower()
    return uc if uc in ("lawn", "garden_beds") else "lawn"


def _skus_from_form(form: dict[str, Any]) -> list[str]:
    raw = form.get("skus") or form.get("products") or []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",")]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        sku = str(item or "").strip().upper()
        if not sku or sku in seen:
            continue
        seen.add(sku)
        out.append(sku)
    return out


_DUAL_USE_ROLES = {
    RoleType.SOIL_STRUCTURE,
    RoleType.SOIL_CHEMISTRY,
    RoleType.BIOLOGY,
    RoleType.UPTAKE,
    RoleType.VISUAL,
}


def _picker_fit(product, *, lawn: bool) -> bool:
    """Lawn=0 in the guide CSV is a ranking hack, not “don’t use on turf”."""
    if product.is_lawn_specialist:
        return lawn
    if product.is_garden_reproductive:
        return not lawn
    if product.role_type in _DUAL_USE_ROLES:
        return True
    lawn_ok = float(product.use_case_scores.get("lawn") or 0) >= 1
    garden_ok = float(product.use_case_scores.get("garden_beds") or 0) >= 1
    return lawn_ok if lawn else garden_ok


def catalog_payload(use_case: str = "lawn") -> dict[str, Any]:
    lawn = use_case != "garden_beds"
    role_order = [
        RoleType.SOIL_STRUCTURE,
        RoleType.SOIL_CHEMISTRY,
        RoleType.BIOLOGY,
        RoleType.UPTAKE,
        RoleType.NUTRITION,
        RoleType.VISUAL,
    ]
    role_labels = {
        RoleType.SOIL_STRUCTURE.value: "Soil structure",
        RoleType.SOIL_CHEMISTRY.value: "Soil pH",
        RoleType.BIOLOGY.value: "Soil life",
        RoleType.UPTAKE.value: "Uptake",
        RoleType.NUTRITION.value: "Feed",
        RoleType.VISUAL.value: "Colour",
    }
    products: list[dict[str, Any]] = []
    for product in _catalog.products:
        if product.role_type == RoleType.BUNDLE:
            continue
        products.append(
            {
                "id": product.id,
                "name": _short_name(product.name),
                "full_name": product.name,
                "role_type": product.role_type.value,
                "image_url": product.image_url,
                "product_url": product.product_url,
                "short_reason": product.short_reason,
                "fit": _picker_fit(product, lawn=lawn),
            }
        )
    products.sort(key=lambda p: (role_order.index(RoleType(p["role_type"])) if p["role_type"] in {r.value for r in role_order} else 99, not p["fit"], p["name"]))
    return {
        "use_case": "lawn" if lawn else "garden_beds",
        "roles": [{"id": r.value, "label": role_labels[r.value]} for r in role_order],
        "products": products,
    }


def _plan_from_products(
    products,
    *,
    start: date,
    area_m2: float | None,
    lawn: bool,
    fungal: bool,
    weed_suppression: bool = False,
    extra_notes: list[str] | None = None,
    choice_summary: list[str] | None = None,
    engine_input: dict[str, Any] | None = None,
    primary: dict[str, Any] | None = None,
    champion_turf_pair: Any = None,
    path: str,
) -> dict[str, Any]:
    plan = build_calendar(
        products,
        intervals=_intervals,
        rates=_rates,
        start=start,
        area_m2=area_m2,
        lawn=lawn,
        fungal=fungal,
        weed_suppression=weed_suppression,
        extra_notes=extra_notes,
        choice_summary=choice_summary,
    )
    plan["ics"] = to_ics(plan["events"])
    plan["path"] = path
    plan["primary"] = primary
    plan["champion_turf_pair"] = champion_turf_pair
    plan["input"] = engine_input or {}
    return plan


def _calendar_payload(form: dict[str, Any]) -> dict[str, Any]:
    start = _parse_start(form.get("start_date"))
    area_m2 = _parse_area(form.get("area_m2"))
    path = str(form.get("path") or "recommend").strip().lower()
    if path in {"pick", "choose", "catalog", "selected"}:
        path = "pick"
    else:
        path = "recommend"

    lawn = _use_case(form) == "lawn"
    fungal = _truthy(form.get("fungal_issues"))
    weed_suppression = _goal_selected(form, "weed_suppression_through_dominance")

    if path == "pick":
        by_id = {p.id.upper(): p for p in _catalog.products}
        products = []
        missing = []
        for sku in _skus_from_form(form):
            product = by_id.get(sku)
            if product is None:
                missing.append(sku)
                continue
            if product.role_type == RoleType.BUNDLE:
                continue
            products.append(product)
        if not products:
            return {
                "error": "Pick at least one product to build a calendar.",
                "path": "pick",
                "events": [],
                "products": [],
                "missing": missing,
            }
        notes = []
        if missing:
            notes.append("Some SKUs were not in the catalog: " + ", ".join(missing) + ".")
        ids = {p.id for p in products}
        if "886" in ids and "892" in ids:
            notes.append(
                "Fairway and Greens Grade are two intensities of the same turf fertiliser — you usually only need one."
            )
        return _plan_from_products(
            products,
            start=start,
            area_m2=area_m2,
            lawn=lawn,
            fungal=fungal,
            weed_suppression=weed_suppression,
            extra_notes=notes,
            choice_summary=["This calendar is built from the products you selected."],
            path="pick",
        )

    engine_input = to_engine_payload(form, start)
    rec = recommend(engine_input, catalog_csv_path=CATALOG_CSV)
    fungal = float(engine_input.get("problems", {}).get("fungal_issues") or 0) >= 0.35
    soils = engine_input.get("soils") or {}
    ph_raw = engine_input.get("soil_ph")
    try:
        ph_val = float(ph_raw) if ph_raw not in (None, "") else None
    except (TypeError, ValueError):
        ph_val = None
    alkaline = float(soils.get("alkaline") or 0) >= 0.35
    acidic = float(soils.get("acidic") or 0) >= 0.35
    if alkaline:
        wants_lime = False
    elif ph_val is not None:
        wants_lime = lime_is_appropriate(ph_val, engine_input.get("soil_ph_method") or "water")
    else:
        wants_lime = acidic

    gw = engine_input.get("goal_weights") or {}
    problems = engine_input.get("problems") or {}
    flowering = (
        float(gw.get("strong_flowering_and_fruiting") or 0) >= 0.35
        or float(problems.get("poor_flowering") or 0) >= 0.35
    )
    deep_green = float(gw.get("deep_green_colour") or 0) >= 0.35
    weed_suppression = float(gw.get("weed_suppression_through_dominance") or 0) >= 0.35
    products, extra_notes = program_products_from_catalog(
        rec,
        _catalog.products,
        wants_lime=wants_lime,
        lawn=engine_input.get("use_case") == "lawn",
        flowering=flowering,
        deep_green=deep_green,
    )
    rec_notes = list((rec.explanations or {}).get("notes") or [])
    plan = _plan_from_products(
        products,
        start=start,
        area_m2=area_m2,
        lawn=engine_input.get("use_case") == "lawn",
        fungal=fungal,
        weed_suppression=weed_suppression,
        extra_notes=extra_notes + rec_notes,
        choice_summary=list((rec.explanations or {}).get("choice_summary") or []),
        engine_input=engine_input,
        primary={
            "id": rec.primary.id,
            "name": rec.primary.name,
            "role_type": rec.primary.role_type.value,
            "image_url": rec.primary.image_url,
            "product_url": rec.primary.product_url,
            "short_reason": rec.primary.short_reason,
        },
        champion_turf_pair=(rec.explanations or {}).get("champion_turf_pair"),
        path="recommend",
    )
    return plan


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(INDEX_HTML)


@app.post("/api/calendar")
async def api_calendar(request: Request) -> dict[str, Any]:
    body = await request.json()
    return _calendar_payload(body or {})


@app.post("/api/calendar.ics")
async def api_ics(request: Request) -> PlainTextResponse:
    body = await request.json()
    plan = _calendar_payload(body or {})
    ics = plan.get("ics") or "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
    return PlainTextResponse(
        ics,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="plant-doctor-calendar.ics"'},
    )


@app.get("/api/catalog")
async def api_catalog(request: Request) -> dict[str, Any]:
    use_case = request.query_params.get("use_case") or "lawn"
    return catalog_payload(use_case)


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "products": len(_catalog.products),
            "intervals": True,
        }
    )

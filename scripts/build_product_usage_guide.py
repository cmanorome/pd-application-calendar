#!/usr/bin/env python3
"""Build machine-readable Product Usage Guide tables from the Aug 2025 PDF.

Outputs (UTF-8 with BOM so Excel opens them cleanly):
  data/product_usage_guide.csv        one row per product — join on sku
  data/product_usage_guide_rates.csv  exploded rate lines from the PDF
  data/product_usage_guide.xlsx       same tables plus legend + mixing rules

Other apps should load the CSV with csv.DictReader(encoding="utf-8-sig")
and treat 0/1 flag columns as booleans.
"""
from __future__ import annotations

import csv
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo
except ImportError:  # pragma: no cover
    Workbook = None  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

FLAG_COLS = (
    "mix_together",
    "independent",
    "water_in",
    "soil_drench",
    "foliar",
    "fertigation",
    "hydroponic",
    "hose_on",
    "mix_with_iron",
    "jar_test",
    "one_off",
    "in_catalog",
)

PRODUCT_COLS = [
    "sku",
    "guide_name",
    "form",
    "pdf_page",
    "analysis",
    "rate_text",
    "min_dilution",
    "frequency_text",
    "cadence_days",
    "cadence_min_days",
    "cadence_max_days",
    "window",
    "max_per_year",
    "one_off",
    "tank_group",
    "method",
    "mix_together",
    "independent",
    "water_in",
    "soil_drench",
    "foliar",
    "fertigation",
    "hydroponic",
    "hose_on",
    "mix_with_iron",
    "jar_test",
    "application_notes",
    "benefits",
    "superpowers",
    "in_catalog",
]

RATE_COLS = ["sku", "guide_name", "use_case", "method", "amount_text", "notes"]

FLAG_LEGEND = [
    ("mix_together", "1", "Overlapping green + gold dots", "Can be mixed together as concentrates before application."),
    ("independent", "1", "Gold dot", "Apply independently — do not tank-mix as a concentrate."),
    ("water_in", "1", "Blue dot", "Water in after application."),
    ("soil_drench", "1", "Terracotta dot", "Suitable as a soil drench."),
    ("foliar", "1", "Green dot", "Suitable as a foliar spray."),
    ("fertigation", "1", "Navy dot", "Suitable through fertigation / irrigation."),
    ("hydroponic", "1", "Teal dot", "Suitable in hydroponics."),
    ("hose_on", "1", "Lime dot, or HOSE ON rates in the PDF", "Hose-on bottle application."),
    ("mix_with_iron", "1", "PDF footnote", "The only product the guide says can be tank-mixed with iron (Stimulizer)."),
    ("jar_test", "1", "Notes column", "Jar-test before mixing with other products."),
    ("tank_group", "mixable | no_iron_mix | iron | granular", "Calendar helper", "How the application calendar groups same-day sprays."),
    ("window", "growing_season | year_round", "Calendar helper", "growing_season skips typical temperate winter."),
    ("sku", "catalog id", "Join key", "Matches Product Guide, Rates Calculator, and Calendar CSVs."),
]

GLOBAL_RULES = [
    ("iron_separate", "Iron products should be applied separately. They can thicken and clog sprayers when mixed with certain products."),
    ("stimulizer_iron_exception", "Stimulizer is the only product the guide says can be safely mixed with iron."),
    ("default_home_rate", "Unless otherwise specified, apply 10 mL per 10 m² (100 mL per 100 m²) of lawn or garden."),
    ("lawn_lovers_tank_example", "Lawn Lovers example per 100 m²: 100 mL Seaweed Secrets + 100 mL Quantum H + 100 mL Activ8mate + 3 mL Stimulizer in the same sprayer."),
    ("water_in_after_most", "After applying most products, lightly water the area to move product into the soil."),
    ("iron_foliar_water_in", "Iron should be applied as a foliar spray and watered in."),
    ("lime_then_iron_days", "42 — wait this many days after lime/dolomite before iron (calendar rule, not printed as a dot)."),
    ("iron_vs_seaweed_gap_days", "3 — keep liquid iron off the same day as seaweed, humic, wetter, and Activ8 (calendar rule)."),
    ("source", "Plant Doctor Product Usage Guide PDF, August 2025, 9 pages."),
    ("contact", "sales@plantdoctor.com.au"),
]


def T(*parts: str) -> str:
    return " ".join(" ".join(parts).split())


def P(
    sku: str,
    guide_name: str,
    form: str,
    pdf_page: int,
    *,
    analysis: str = "",
    rate_text: str,
    min_dilution: str = "",
    frequency_text: str,
    cadence_days: int,
    cadence_min_days: int = 0,
    cadence_max_days: int = 0,
    window: str,
    max_per_year: int,
    one_off: int = 0,
    tank_group: str,
    method: str,
    mix_together: int = 0,
    independent: int = 0,
    water_in: int = 0,
    soil_drench: int = 0,
    foliar: int = 0,
    fertigation: int = 0,
    hydroponic: int = 0,
    hose_on: int = 0,
    mix_with_iron: int = 0,
    jar_test: int = 0,
    application_notes: str,
    benefits: str,
    superpowers: str,
    in_catalog: int = 1,
    rates: list[dict] | None = None,
) -> tuple[dict, list[dict]]:
    row = {
        "sku": sku,
        "guide_name": guide_name,
        "form": form,
        "pdf_page": pdf_page,
        "analysis": analysis,
        "rate_text": T(rate_text),
        "min_dilution": min_dilution,
        "frequency_text": T(frequency_text),
        "cadence_days": cadence_days,
        "cadence_min_days": cadence_min_days or cadence_days,
        "cadence_max_days": cadence_max_days or cadence_days,
        "window": window,
        "max_per_year": max_per_year,
        "one_off": one_off,
        "tank_group": tank_group,
        "method": method,
        "mix_together": mix_together,
        "independent": independent,
        "water_in": water_in,
        "soil_drench": soil_drench,
        "foliar": foliar,
        "fertigation": fertigation,
        "hydroponic": hydroponic,
        "hose_on": hose_on,
        "mix_with_iron": mix_with_iron,
        "jar_test": jar_test,
        "application_notes": T(application_notes),
        "benefits": T(benefits),
        "superpowers": T(superpowers),
        "in_catalog": in_catalog,
    }
    rate_rows = []
    for item in rates or [{"use_case": "general", "method": method, "amount_text": T(rate_text), "notes": ""}]:
        rate_rows.append(
            {
                "sku": sku,
                "guide_name": guide_name,
                "use_case": item["use_case"],
                "method": item.get("method") or method,
                "amount_text": T(item["amount_text"]),
                "notes": T(item.get("notes") or ""),
            }
        )
    return row, rate_rows


def catalog() -> tuple[list[dict], list[dict]]:
    products: list[dict] = []
    rates: list[dict] = []

    def add(*args, **kwargs):
        row, rate_rows = P(*args, **kwargs)
        products.append(row)
        rates.extend(rate_rows)

    add(
        "A8X",
        "Activ8EXTRA",
        "liquid",
        2,
        analysis="16-2-5 NPK + seaweed, fish, blood & bone, humic, fulvic",
        rate_text="75–100 mL per 100 m²",
        min_dilution="1:100",
        frequency_text="Apply fortnightly during spring and summer. Reduce frequency and/or application strength during cooler months. Suitable for year-round use to support soil biology.",
        cadence_days=14,
        window="growing_season",
        max_per_year=16,
        tank_group="no_iron_mix",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        jar_test=1,
        application_notes="Agitate well before use. Apply with sufficient water for even coverage and lightly water in if required. You can choose to lightly water in or leave on the leaf to dry prior to a light watering. Suitable for foliar, soil and fertigation applications. Compatible with most liquid fertilisers; always jar test before tank mixing.",
        benefits="A high-performance liquid fertiliser and soil conditioner that promotes rapid green growth while improving soil biology, nutrient availability and plant resilience. Helps inoculate turf, grass and soil, supports the conversion of fertilisers into plant-available nutrients, improves water penetration, reduces runoff and helps stabilise nutrients within the rhizosphere for longer-lasting plant access.",
        superpowers="Traditional 16-2-5 NPK | Enriched with seaweed extract, fish, blood & bone, humic acid and fulvic acid | Feeds beneficial microbes | Buffers salts | Increases micronutrient availability | Improves nutrient use efficiency | Creates a healthier root zone by enhancing soil aeration, microbial activity and nutrient cycling.",
        rates=[{"use_case": "lawn_garden", "method": "spray", "amount_text": "75–100 mL / 100 m²", "notes": "Minimum dilution 1:100"}],
    )
    add(
        "A8M",
        "Activ8mate",
        "liquid",
        2,
        analysis="8-1-4 NPK + seaweed, fish, humic, fulvic, traces",
        rate_text="100 mL per 100 m²",
        min_dilution="1:100",
        frequency_text="Apply fortnightly during warmer months for active growth. During cooler months, reduce frequency or apply at a lower strength. Suitable for year-round soil and plant health programs.",
        cadence_days=14,
        window="growing_season",
        max_per_year=16,
        tank_group="no_iron_mix",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        application_notes="Shake well before use. Apply evenly across lawns, gardens, vegetables, trees and natives. Light watering after application helps move nutrients into the soil and activate microbial processes. Suitable for foliar, soil and fertigation applications. Avoid mixing with iron products.",
        benefits="A complete liquid fertiliser and soil conditioner that feeds lawns, plants and trees while improving soil biology, nutrient availability and root zone health. Helps stabilise nutrients in the rhizosphere, keeping them available for longer and improving nutrient efficiency. Supports stronger growth, healthier roots and improved resilience to environmental stress.",
        superpowers="Traditional 8-1-4 NPK | Enriched with seaweed extract, fish, humic acid, fulvic acid, trace elements and beneficial microbial stimulants | Supports microbial activity | Improves nutrient conversion and chelation | Enhances soil structure | Increases water retention | Helps stabilise nutrients within the rhizosphere for longer plant availability.",
        rates=[{"use_case": "lawn_garden", "method": "spray", "amount_text": "100 mL / 100 m²", "notes": "Minimum dilution 1:100"}],
    )
    add(
        "886",
        "Champion Lawn & Fairway 2-4mm granular fertiliser",
        "granular",
        2,
        analysis="15.1-3-8.9 NPK + 7.3% silica, 3.8% S, 3.4% Fe + VolcaMin",
        rate_text="20–40 g per m² (2–4 kg per 100 m²). Half rate in autumn and winter.",
        frequency_text="Apply every 8–12 weeks during the active growing season (spring to autumn). Provides up to 3 months of sustained nutrition. Apply at 1/2 the rate during autumn and winter.",
        cadence_days=84,
        cadence_min_days=56,
        cadence_max_days=84,
        window="growing_season",
        max_per_year=4,
        tank_group="granular",
        method="spread",
        independent=1,
        water_in=1,
        application_notes="Apply evenly using a broadcast spreader. Water in lightly after application to activate nutrients. Avoid applying during the heat of the day or when temperatures exceed 30°C. Suitable for residential lawns, fairways, tees, sports turf and professional turf applications.",
        benefits="A premium slow-release mineral fertiliser that provides consistent nutrition for greener, denser and more resilient turf. Improves nutrient efficiency, reduces leaching and runoff, strengthens plant growth, and supports better stress tolerance, disease resistance and long-term turf performance. Includes VolcaMin zeolite technology which acts as a natural molecular sieve and nutrient-holding super sponge.",
        superpowers="15.1-3-8.9 NPK | 7.3% Silica | 3.8% Sulphur | 3.4% Iron | VolcaMin zeolite technology | Helps stabilise nutrients in the soil, releasing them gradually when plants and microbes require them.",
        rates=[
            {"use_case": "lawn_growing_season", "method": "spread", "amount_text": "20–40 g/m² (2–4 kg/100 m²)"},
            {"use_case": "autumn_winter", "method": "spread", "amount_text": "half rate", "notes": "1/2 the growing-season rate"},
        ],
    )
    add(
        "892",
        "Champion Lawn & Greens Mini-Prill Fertiliser",
        "granular",
        2,
        analysis="16.8-1.1-9.1 NPK + 8% silica, 3.15% Fe + VolcaMin",
        rate_text="20–40 g per m² (2–4 kg per 100 m²). Half rate in autumn and winter.",
        frequency_text="Apply every 8–12 weeks during the active growing season (spring to autumn). Provides up to 3 months of sustained nutrition. Apply at 1/2 the rate during autumn and winter.",
        cadence_days=84,
        cadence_min_days=56,
        cadence_max_days=84,
        window="growing_season",
        max_per_year=4,
        tank_group="granular",
        method="spread",
        independent=1,
        water_in=1,
        application_notes="Apply evenly using a suitable spreader for fine turf applications. The 1–2 mm mini-prill size provides excellent distribution across low-cut lawns, greens and high-performance turf. Lightly water after application to activate nutrients and minimise the risk of leaf burn.",
        benefits="A premium greens-grade slow-release mineral fertiliser designed for fine turf, low-cut lawns and professional sporting surfaces. Provides an initial colour response followed by sustained feeding for up to 3 months.",
        superpowers="16.8-1.1-9.1 NPK | 8% Silica | 3.15% Iron | VolcaMin zeolite technology | Essential trace elements | Helps stabilise nitrogen | Improve phosphorus availability | Retain iron in the root zone | High silica for heat, drought, disease and wear tolerance.",
        rates=[
            {"use_case": "fine_turf_growing_season", "method": "spread", "amount_text": "20–40 g/m² (2–4 kg/100 m²)"},
            {"use_case": "autumn_winter", "method": "spread", "amount_text": "half rate"},
        ],
    )
    add(
        "DOL",
        "Dolomite Granules",
        "granular",
        3,
        analysis="Calcium magnesium carbonate (dolomite)",
        rate_text="5 kg per 100 m² (may vary with soil pH and magnesium levels).",
        frequency_text="Apply during autumn or early spring for best results. Can be used as part of a regular soil improvement program or before planting and lawn establishment.",
        cadence_days=365,
        window="year_round",
        max_per_year=1,
        one_off=1,
        tank_group="granular",
        method="spread",
        water_in=1,
        application_notes="Test soil pH and magnesium levels before application. Apply evenly across the area and water in to help granules break down. Avoid over-application, as excessive use can create nutrient imbalances.",
        benefits="A soil conditioner that helps neutralise acidic soils while supplying essential calcium and magnesium for stronger roots, healthier plants and improved nutrient availability.",
        superpowers="Calcium magnesium carbonate (dolomite) | Calcium for cell walls, roots and soil structure | Magnesium for chlorophyll | Helps optimise soil pH, unlocking N, P and K.",
        rates=[{"use_case": "soil_amendment", "method": "spread", "amount_text": "5 kg / 100 m²", "notes": "Adjust to pH and magnesium test"}],
    )
    add(
        "575",
        "Flowers, Fruits & Roots - Granular",
        "granular",
        3,
        analysis="8-2-20 NPK + 8.8% S, 6.9% silica, Ca, Mg, traces",
        rate_text="2–5.5 kg per 100 m² depending on plant type.",
        frequency_text="Apply during active growth, flowering and fruiting periods. Suitable for year-round use where plants require additional potassium and mineral nutrition.",
        cadence_days=120,
        window="growing_season",
        max_per_year=3,
        tank_group="granular",
        method="spread",
        water_in=1,
        application_notes="Apply evenly around plants and water in well after application. Suitable for flowers, vegetables, herbs, fruit trees, ornamental plants and lawns. Use caution with phosphorus-sensitive natives such as grevilleas, banksias and proteas.",
        benefits="A high-potassium mineral fertiliser designed to support stronger roots, vibrant flowers, improved fruit development and healthier plants.",
        superpowers="8-2-20 NPK | 8.8% Sulphur | 6.9% Silica | Calcium | Magnesium | Essential trace elements | High potassium for flower initiation, fruit and stress tolerance | Silica strengthens plant cells.",
        rates=[
            {"use_case": "general", "method": "spread", "amount_text": "2–5.5 kg / 100 m²"},
            {"use_case": "roses", "method": "spread", "amount_text": "70 g/m²"},
            {"use_case": "fruit_trees", "method": "spread", "amount_text": "20–40 g per tree"},
            {"use_case": "pots", "method": "spread", "amount_text": "2 g per litre of potting mix"},
            {"use_case": "turf", "method": "spread", "amount_text": "20–40 g/m²", "notes": "Guide lists turf rate; catalog treats this SKU as garden flower/fruit, not a lawn fertiliser."},
        ],
    )
    add(
        "721",
        "Flowers, Fruits & Roots - Liquid",
        "liquid",
        3,
        analysis="9-7-19 NPK + humic, seaweed, traces",
        rate_text="80–120 mL per 100 m² depending on plant type.",
        frequency_text="Apply every 4 weeks during flowering/fruiting. Vegetables can be applied fortnightly when actively producing. Trees, fruit and vines can be applied every 6–8 weeks as required.",
        cadence_days=28,
        cadence_min_days=14,
        cadence_max_days=56,
        window="growing_season",
        max_per_year=10,
        tank_group="mixable",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        application_notes="Apply evenly to soil or foliage during the cooler parts of the day. Shake well before use. Suitable for flowers, vegetables, fruit trees, herbs, ornamental plants and turf. Use caution with phosphorus-sensitive native plants.",
        benefits="A fast-acting high-potassium liquid fertiliser designed to support flowering, fruit development and stronger root growth.",
        superpowers="9-7-19 NPK | Humic acid | Seaweed extract | Traces including Fe, Zn, Mn, Cu, B, Mg, Mo | High potassium for flowering and fruit fill | Humic compounds improve nutrient availability.",
        rates=[
            {"use_case": "general", "method": "spray", "amount_text": "80–120 mL / 100 m²"},
            {"use_case": "ornamentals", "method": "spray", "amount_text": "10–20 mL per 8 L water"},
            {"use_case": "vegetables", "method": "spray", "amount_text": "10–20 mL per 8 L water", "notes": "Fortnightly when producing"},
            {"use_case": "trees_fruit_vines", "method": "spray", "amount_text": "100–170 mL / 100 m²", "notes": "Every 6–8 weeks"},
        ],
    )
    add(
        "414",
        "Fulvic Acid Liquid",
        "liquid",
        3,
        analysis="High-grade fulvic acid",
        rate_text="Varies by application type.",
        frequency_text="Apply weekly or fortnightly as required throughout the growing season. Suitable for year-round use across turf, gardens, vegetables, fruit trees, hydroponics and agricultural systems.",
        cadence_days=14,
        cadence_min_days=7,
        cadence_max_days=14,
        window="year_round",
        max_per_year=24,
        tank_group="no_iron_mix",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        hydroponic=1,
        jar_test=1,
        application_notes="Can be applied through soil, foliar sprays, fertigation or hydroponic systems. Compatible with most fertilisers, soil conditioners and crop inputs; always conduct a jar test before tank mixing.",
        benefits="A powerful bio-stimulant and soil conditioner that improves nutrient availability, enhances fertiliser efficiency and supports stronger root and plant growth.",
        superpowers="High-grade fulvic acid | Natural chelating agent | Improves nutrient uptake efficiency | Supports microbial activity | Enhances root development | Helps stabilise fertilisers in the soil | Small molecules move rapidly through plant tissues.",
        rates=[
            {"use_case": "home_garden", "method": "watering_can", "amount_text": "15 mL per watering can"},
            {"use_case": "hydroponics", "method": "hydroponic", "amount_text": "1800 mL per 1000 L water"},
            {"use_case": "foliar_turf", "method": "foliar", "amount_text": "1450 mL per 1000 L water"},
            {"use_case": "broadacre", "method": "spray", "amount_text": "3900 mL per 1000 L water/ha"},
        ],
    )
    add(
        "29814",
        "Fulvic Acid Powder >92%",
        "powder",
        4,
        analysis=">92% fulvic acid, CEC ~1400",
        rate_text="Varies by application type.",
        frequency_text="Apply throughout the growing season as required. Particularly beneficial during seeding, transplanting, flowering, fruiting, nutrient deficiencies, and periods of plant stress.",
        cadence_days=21,
        window="growing_season",
        max_per_year=12,
        tank_group="no_iron_mix",
        method="spray",
        soil_drench=1,
        foliar=1,
        fertigation=1,
        hydroponic=1,
        jar_test=1,
        application_notes="Fully soluble powder suitable for fertigation, foliar sprays, soil drenches and hydroponic systems. Can be combined with fertilisers to improve nutrient efficiency. Always conduct a jar test before mixing with new products, especially selective herbicides. Store sealed and dry.",
        benefits="A highly concentrated bio-stimulant that improves nutrient availability, enhances fertiliser efficiency and supports stronger plant growth.",
        superpowers=">92% fulvic acid concentrate | CEC ~1400 | Powerful natural chelator | Enhances microbial activity | Supports root development | Improves fertiliser performance.",
        rates=[
            {"use_case": "fertigation", "method": "fertigation", "amount_text": "500 g–1 kg/ha"},
            {"use_case": "foliar", "method": "foliar", "amount_text": "300–500 g/ha"},
            {"use_case": "broadacre", "method": "spray", "amount_text": "80–150 g/ha"},
            {"use_case": "hydroponics", "method": "hydroponic", "amount_text": "5–10 g per 10 L water"},
        ],
    )
    add(
        "1075",
        "Gypsum Granules 1–2mm Mini Prill",
        "granular",
        4,
        analysis="19% Ca, 14% S",
        rate_text="100 g per m² (10 kg per 100 m²). Ideally based on soil analysis.",
        frequency_text="Apply when soils are compacted, heavy clay, sodic, or calcium deficient. Ideal during soil preparation, before planting, or as part of an ongoing soil improvement program.",
        cadence_days=365,
        window="year_round",
        max_per_year=1,
        one_off=1,
        tank_group="granular",
        method="spread",
        water_in=1,
        application_notes="Apply evenly across the soil surface and water in after application to assist movement into the soil profile. Suitable for lawns, gardens, landscaping, parks, ovals and agricultural applications.",
        benefits="A slow-release calcium sulphate soil conditioner that improves soil structure, reduces compaction and supports healthier root growth without significantly changing soil pH.",
        superpowers="19% Calcium | 14% Sulphur | Improves soil aggregation | Displaces excess sodium in sodic soils | 1–2 mm mini prill for even spreading with minimal dust.",
        rates=[{"use_case": "soil_amendment", "method": "spread", "amount_text": "100 g/m² (10 kg/100 m²)", "notes": "Confirm with soil test where possible"}],
    )
    add(
        "513",
        "Humate / Humic Acid Granules (45–50%)",
        "granular",
        4,
        analysis="45–50% humic acid from leonardite",
        rate_text="2–5 kg per 100 m² depending on plant type.",
        frequency_text="Apply every 3 months as part of an ongoing soil improvement program. Ideal before planting, during establishment, after fertiliser application, or whenever soils have poor nutrient availability, low organic carbon or reduced microbial activity.",
        cadence_days=90,
        window="year_round",
        max_per_year=4,
        tank_group="granular",
        method="spread",
        water_in=0,
        application_notes="Apply evenly by hand or broadcast spreader onto the top layer of soil, under mulch, or dug in. Does not need to be watered in. Suitable for lawns, vegetables, fruit trees, crops, ornamentals and all soil types. Can be applied alongside fertilisers, side dressing, seeding and planting.",
        benefits="A concentrated organic soil conditioner that improves soil structure, nutrient retention and microbial activity.",
        superpowers="45–50% humic acid from leonardite | Improves CEC | Holds nutrients in the root zone | Supports beneficial microbes | Enhances soil structure | Reduces leaching and volatilisation.",
        rates=[
            {"use_case": "lawns_turf", "method": "spread", "amount_text": "2–5 kg / 100 m²"},
            {"use_case": "gardens", "method": "spread", "amount_text": "2–5 kg / 100 m² or a handful per plant/pot"},
            {"use_case": "potting_mix", "method": "incorporate", "amount_text": "2.5–10% inclusion rate"},
        ],
    )
    add(
        "526",
        "Humic acid 80% (Humate) Powder - 99% Soluble",
        "powder",
        4,
        analysis="80% humic acid, 99% soluble potassium humate",
        rate_text="Varies by application type.",
        frequency_text="Apply every 2–4 weeks during active growth, or as required when soils have poor nutrient availability, low organic carbon, salt stress or reduced biological activity.",
        cadence_days=21,
        cadence_min_days=14,
        cadence_max_days=28,
        window="growing_season",
        max_per_year=12,
        tank_group="no_iron_mix",
        method="spray",
        soil_drench=1,
        foliar=1,
        fertigation=1,
        jar_test=1,
        application_notes="Pre-mix powder in water before application to ensure complete dissolution. Apply as a soil drench, foliar spray or through fertigation. Can be used alongside fertilisers and biological inputs, but perform a jar test before mixing.",
        benefits="Improves soil health by increasing nutrient availability, supporting beneficial microbes, improving water retention and enhancing fertiliser efficiency.",
        superpowers="80% humic acid from premium leonardite | 99% solubility | Potassium humate chelator and carbon source | Helps unlock phosphorus | Binds salts and residues | Improves soil structure.",
        rates=[
            {"use_case": "foliar", "method": "foliar", "amount_text": "1–3 kg per 1000 L water"},
            {"use_case": "soil_fertigation", "method": "fertigation", "amount_text": "5–10 kg per 1000 L water"},
            {"use_case": "home_garden", "method": "drench", "amount_text": "10–30 g per 10 L water"},
            {"use_case": "new_plants", "method": "drench", "amount_text": "2 g per litre of water"},
        ],
    )
    add(
        "547",
        "Iron Chelate Microgranules",
        "powder",
        5,
        analysis="13% Fe as EDTA chelate (130 g/kg)",
        rate_text="Varies by application type.",
        frequency_text="Apply from spring through autumn, especially at the start of active growth or whenever signs of iron deficiency appear, such as yellowing leaves, pale colour or reduced plant vigour.",
        cadence_days=28,
        window="growing_season",
        max_per_year=6,
        tank_group="iron",
        method="spray",
        independent=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        jar_test=1,
        application_notes="Dissolve microgranules fully in water before application. Can be applied as a foliar spray, soil drench, pressure injection or through fertigation. Unlike iron sulphate, it is compatible with most fertilisers, but a jar test is recommended before mixing. Avoid contact with concrete and porous surfaces as staining may occur.",
        benefits="Quickly corrects iron deficiency and chlorosis while restoring deep green colour, supporting healthy leaf development, photosynthesis and stronger plant growth.",
        superpowers="13% Iron (Fe) as EDTA chelate | Fully water-soluble microgranules | Remains stable in the soil | Fast-acting correction of yellowing leaves.",
        rates=[
            {"use_case": "flowers_vegetables", "method": "drench", "amount_text": "10 g per 10 L water", "notes": "Covers 10 m²"},
            {"use_case": "fruit_trees", "method": "drench", "amount_text": "35 g per 10 L water", "notes": "Root zone"},
            {"use_case": "roses_shrubs", "method": "drench", "amount_text": "25 g per 10 L water per plant"},
            {"use_case": "lawn_drench", "method": "drench", "amount_text": "25 g per 5 L water"},
            {"use_case": "lawn_foliar", "method": "foliar", "amount_text": "5 g per 5 L water"},
        ],
    )
    add(
        "846",
        "Iron Sulphate Heptahydrate Powder",
        "powder",
        5,
        analysis="19.5% Fe, 11.5% S",
        rate_text="Varies by application goal.",
        frequency_text="Apply when lawns show signs of iron deficiency, poor colour, alkaline soil, or moss growth. For moss prevention, apply every 6–8 weeks from late autumn through winter and early spring.",
        cadence_days=28,
        cadence_min_days=42,
        cadence_max_days=56,
        window="growing_season",
        max_per_year=4,
        tank_group="iron",
        method="spread",
        independent=1,
        water_in=1,
        application_notes="Apply evenly using a broadcast spreader or dilute in water and spray. Water thoroughly after application. Avoid applying on windy days and wear protective gloves and a dust mask. Can stain concrete, paths and clothing.",
        benefits="A slow-release iron source that promotes deep green colour, corrects iron deficiency, supports healthier turf growth and helps gently acidify alkaline soils, reducing moss growth.",
        superpowers="19.5% Iron (Fe) | 11.5% Sulphur (S) | Slow-release ferrous sulphate store of iron in the soil.",
        rates=[
            {"use_case": "iron_deficiency", "method": "spread", "amount_text": "20–30 g/m²"},
            {"use_case": "soil_ph_adjustment", "method": "spread", "amount_text": "25–35 g/m²"},
            {"use_case": "moss_control", "method": "spread", "amount_text": "10–20 g/m²"},
        ],
    )
    add(
        "LEN",
        "Lawn Envy",
        "hose-on",
        5,
        analysis="Concentrate 16-1-5 NPK + 1% Fe EDTA; hose-on 8-1-3 NPK + iron",
        rate_text="2 L hose-on covers up to 200 m². 1 L concentrate: mix into the 2 L hose-on bottle or use with EZFLO.",
        frequency_text="Apply year-round for ongoing lawn and garden health. Ideal during nutrient stress, dull colour, dry patches, hydrophobic soils, post-mowing recovery and general maintenance.",
        cadence_days=28,
        window="year_round",
        max_per_year=12,
        tank_group="iron",
        method="hose-on",
        independent=1,
        water_in=1,
        hose_on=1,
        application_notes="HOSE ON: connect the hose-on bottle and spray evenly. For refills, reuse the bottle with 4 L or 10 L concentrate packs. Can also be added to EZFLO. CONCENTRATE: shake well, apply during the coolest part of the day, lightly water in. Apply separately from most liquid fertilisers and pesticides.",
        benefits="An all-in-one lawn and garden tonic combining fertiliser, seaweed, iron chelate, soil wetter and organic stimulants.",
        superpowers="16-1-5 NPK + 1% Iron EDTA (concentrate) | 8-1-3 NPK + iron (hose-on) | Cold-processed Ascophyllum nodosum | Activ8EXTRA | Humic & fulvic acids | Nature's Soil Wetter.",
        rates=[
            {"use_case": "hose_on", "method": "hose-on", "amount_text": "2 L covers up to 200 m²"},
            {"use_case": "concentrate", "method": "hose-on", "amount_text": "1 L concentrate into 2 L hose-on bottle or EZFLO"},
        ],
    )
    add(
        "LIMEGr",
        "Lime Granules 1-2mm Slow Release",
        "granular",
        5,
        analysis="Calcium carbonate (CaCO3)",
        rate_text="Varies by soil type to raise pH by about 1 unit.",
        frequency_text="Apply when soil tests indicate acidic soil (low pH). Best applied in autumn or early spring before planting or as part of a seasonal soil improvement program.",
        cadence_days=365,
        window="year_round",
        max_per_year=1,
        one_off=1,
        tank_group="granular",
        method="spread",
        water_in=1,
        application_notes="Spread evenly over the soil surface and water in well. Where possible, incorporate into the topsoil. Always perform a soil test before application to determine the correct rate. Wait 6 weeks before applying iron.",
        benefits="Raises soil pH to reduce acidity, improving nutrient availability, fertiliser efficiency and overall soil health.",
        superpowers="Calcium carbonate | Slow-release calcium | Neutralises soil acidity | Reduces aluminium and manganese toxicity.",
        rates=[
            {"use_case": "sandy", "method": "spread", "amount_text": "50–75 g/m²"},
            {"use_case": "loam", "method": "spread", "amount_text": "75–100 g/m²"},
            {"use_case": "clay", "method": "spread", "amount_text": "100–150 g/m²", "notes": "To raise pH by ~1 unit"},
        ],
    )
    add(
        "LIR",
        "Liquid Iron Fertiliser - 7% Iron 3% Sulphur",
        "liquid",
        6,
        analysis="7% Fe, 3% S + fulvic acid",
        rate_text="150–400 mL per 100 m² depending on plant type.",
        min_dilution="1:50",
        frequency_text="Apply every 4 weeks during the growing season, or as required to correct iron deficiency and improve colour. Trees and grapevines can be applied every 6–8 weeks.",
        cadence_days=28,
        cadence_min_days=28,
        cadence_max_days=56,
        window="growing_season",
        max_per_year=8,
        tank_group="iron",
        method="spray",
        independent=1,
        water_in=1,
        jar_test=1,
        application_notes="Apply as a foliar spray or soil drench during the coolest part of the day. Can be mixed with Stimulizer, but should be applied separately from most other fertilisers and liquid products. Always perform a jar test before mixing.",
        benefits="Quickly corrects iron deficiency and chlorosis while promoting deep green colour, healthier foliage and improved chlorophyll production.",
        superpowers="7% Iron (Fe) | 3% Sulphur (S) + fulvic acid | Fulvic acid enhances uptake and translocation | Can be mixed with Stimulizer concentrate.",
        rates=[
            {"use_case": "general", "method": "spray", "amount_text": "150–400 mL / 100 m²", "notes": "Minimum dilution 1:50"},
            {"use_case": "vegetables_trees_ornamentals", "method": "spray", "amount_text": "150–300 mL / 100 m² or 10–25 mL per 10 L water"},
        ],
    )
    add(
        "MG",
        "MaxGreen Hi-N & Iron liquid fertiliser",
        "hose-on",
        6,
        analysis="16% N, 5% Fe, 2% S + fulvic acid",
        rate_text="2 L hose-on covers 200 m². Concentrate 140–400 mL per 100 m².",
        frequency_text="Apply monthly during the growing season for lawns and ornamentals, fortnightly for vegetables, and every 6–8 weeks for trees, fruit, nuts and grapevines, or as required.",
        cadence_days=28,
        cadence_min_days=14,
        cadence_max_days=56,
        window="growing_season",
        max_per_year=8,
        tank_group="iron",
        method="hose-on",
        independent=1,
        water_in=1,
        hose_on=1,
        jar_test=1,
        application_notes="HOSE ON: connect bottle and spray evenly; refill with 4 L or 10 L concentrate; EZFLO compatible. CONCENTRATE: shake well, apply in the coolest part of the day, lightly water in. Apply separately from most liquid fertilisers and pesticides. Stimulizer is compatible for tank mixing.",
        benefits="Delivers a rapid boost of nitrogen and iron to promote lush growth, correct iron deficiency and produce rich green colour.",
        superpowers="16% Nitrogen | 5% Iron | 2% Sulphur + fulvic acid | Can be mixed with Stimulizer concentrate.",
        rates=[
            {"use_case": "hose_on", "method": "hose-on", "amount_text": "2 L covers 200 m²"},
            {"use_case": "concentrate", "method": "spray", "amount_text": "140–400 mL / 100 m²"},
            {"use_case": "vegetables_trees_ornamentals", "method": "spray", "amount_text": "140–300 mL / 100 m² or 10–25 mL per 9 L water"},
        ],
    )
    add(
        "636",
        "Micronised Gypsum Liquid",
        "liquid",
        6,
        analysis="16.5% Ca, 13% S",
        rate_text="Home garden: 45 mL in 9 L water, apply 1 L/m² (500 mL per 100 m²). Soil ameliorant or fertigation: 10–50 L/ha. Foliar: 1 L per 100 L water, up to 5–7 L/ha depending on crop.",
        min_dilution="1:3",
        frequency_text="Apply every 2–4 weeks, or as required, to improve clay soils, correct calcium and sulphur deficiencies, and support ongoing soil conditioning. Higher rates for heavy clay soils.",
        cadence_days=21,
        cadence_min_days=14,
        cadence_max_days=28,
        window="growing_season",
        max_per_year=12,
        tank_group="no_iron_mix",
        method="spray",
        soil_drench=1,
        foliar=1,
        fertigation=1,
        jar_test=1,
        application_notes="Shake or stir well before use and keep agitating. Pre-mix slowly. Will pass a 200-micron filter under ideal conditions; a coarse inline filter (500 micron / 35 mesh) is recommended. Drench with a watering can or equipment that can take larger particles. Not suitable for drippers. Foliar use can leave a visible residue on leaves and fruit. Jar test before mixing. Liquid inject minimum dilution 1-part product to 3-parts water. Store cool and keep sealed.",
        benefits="Improves soil structure by breaking up heavy clay and compacted soils while supplying readily available calcium and sulphur.",
        superpowers="16.5% Calcium | 13% Sulphur | Ultra-fine micronised gypsum | Displaces excess sodium and magnesium | Improves aeration and fertiliser efficiency.",
        rates=[
            {"use_case": "home_garden", "method": "drench", "amount_text": "45 mL per 9 L water", "notes": "Apply 1 L/m² every 2–4 weeks (500 mL per 100 m²)"},
            {"use_case": "soil_amelioration_fertigation", "method": "fertigation", "amount_text": "10–50 L/ha", "notes": "Use higher rates for heavy clay"},
            {"use_case": "foliar_vegetables", "method": "foliar", "amount_text": "1 L per 100 L water, up to 5 L/ha", "notes": "Weekly or as required"},
            {"use_case": "foliar_orchards_vineyards", "method": "foliar", "amount_text": "1 L per 100 L water, up to 7 L/ha", "notes": "Every 2–4 weeks or as required"},
            {"use_case": "foliar_ornamentals_turf", "method": "foliar", "amount_text": "1 L per 100 L water, up to 5 L/ha", "notes": "Every 2–4 weeks or as required"},
            {"use_case": "broadacre_crops_pasture", "method": "spray", "amount_text": "1–3 L/ha in 60–100 L water", "notes": "Depending on canopy closure"},
            {"use_case": "spot_spraying", "method": "spray", "amount_text": "50 mL per 10 L water", "notes": "Apply as required"},
            {"use_case": "liquid_inject", "method": "inject", "amount_text": "2–5 L/ha", "notes": "Minimum dilution 1:3"},
        ],
    )
    add(
        "NSWL",
        "Nature's Soil Wetter - Liquid",
        "liquid",
        6,
        analysis="Plant-derived wetter + humates, fulvates, botanical extracts, 70+ traces",
        rate_text="100 mL per 100 m²",
        frequency_text="Apply every 2–4 weeks, or as required, when soils become dry, water repellent or compacted. Ideal during dry periods or whenever water struggles to penetrate the soil profile.",
        cadence_days=21,
        cadence_min_days=14,
        cadence_max_days=28,
        window="growing_season",
        max_per_year=12,
        tank_group="no_iron_mix",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        jar_test=1,
        application_notes="Mix gently before use, do not shake. Water in lightly after application to activate the product. Compatible with most fertilisers, although a jar test is recommended before mixing with acidic or sulphate-based products.",
        benefits="Breaks down water-repellent soils, improves water penetration and moisture retention, and enhances fertiliser efficiency.",
        superpowers="Plant-derived soil wetting agent | Complex organic compounds, natural humates, fulvates and botanical extracts | Improves soil structure | Stabilises nitrogen | Binds salts and toxins | Buffers soil pH | 70+ naturally occurring trace minerals.",
        rates=[{"use_case": "lawn_garden", "method": "spray", "amount_text": "100 mL / 100 m²", "notes": "Do not shake"}],
    )
    add(
        "664",
        "Nature's Soil Wetter granules",
        "granular",
        7,
        analysis="Plant-derived surfactants + zeolite + botanical extracts + 70+ traces",
        rate_text="Varies by surface type.",
        frequency_text="Apply when soils become water repellent, dry, compacted or struggle to absorb moisture. Ideal as part of regular soil maintenance, during dry periods, or when improving soil structure.",
        cadence_days=120,
        cadence_min_days=30,
        cadence_max_days=180,
        window="growing_season",
        max_per_year=3,
        tank_group="granular",
        method="spread",
        water_in=1,
        application_notes="Apply evenly as a top-dress using a spreader or incorporate into potting mixes and garden beds. Watering after application is recommended to activate the granules, although not essential. Apply under tree drip lines or beneath mulch for fruit trees and natives.",
        benefits="Improves water penetration, moisture retention and soil structure while reducing hydrophobic conditions.",
        superpowers="Plant-derived surfactants | Zeolite mineral matrix | Botanical extracts | 70+ naturally occurring trace minerals | Improves water distribution | Increases nutrient retention | Supports microbes | Buffers pH | Helps stabilise nitrogen.",
        rates=[
            {"use_case": "lawns_gardens", "method": "spread", "amount_text": "1.5–2 kg / 100 m² every 3–6 months"},
            {"use_case": "golf_greens", "method": "spread", "amount_text": "1.5 kg / 100 m² every 1–2 months"},
            {"use_case": "fairways_sports", "method": "spread", "amount_text": "2 kg / 100 m² every 2–3 months"},
            {"use_case": "crops_vegetables", "method": "spread", "amount_text": "1.5–2 kg / 100 m²"},
        ],
    )
    add(
        "758",
        "Neem Fertiliser Slow Release Granules",
        "granular",
        7,
        analysis="1-1-4 NPK + VolcaMin + neem oil + soil wetter",
        rate_text="50–100 g per m²",
        frequency_text="Apply 1–2 times per year for ongoing soil improvement and long-term fertility. Ideal during turf renovation, lawn recovery, before planting, or when soils need improved nutrient retention.",
        cadence_days=180,
        window="year_round",
        max_per_year=2,
        tank_group="granular",
        method="spread",
        water_in=1,
        application_notes="Apply evenly over the soil surface and, where possible, incorporate into the top 10 cm of soil. Can be applied before sowing, laying turf, or swept into aeration holes. Water in lightly after application to activate the neem and soil wetter components.",
        benefits="A natural slow-release fertiliser and soil conditioner that provides steady nutrition while improving soil structure, water retention and nutrient availability. Feeds plants for up to 3 months.",
        superpowers="1-1-4 NPK | VolcaMin zeolite | Neem oil | Natural soil wetter | Feeds up to 3 months | Improves CEC, water holding and plant resilience.",
        rates=[{"use_case": "soil_amendment", "method": "spread", "amount_text": "50–100 g/m²"}],
    )
    add(
        "NSO",
        "Neem Seed Oil - 100% Cold Pressed virgin oil",
        "oil",
        7,
        analysis="100% cold-pressed Azadirachta indica oil",
        rate_text="Varies by application type.",
        frequency_text="Apply during active plant growth, as part of a preventative plant care routine, or when plants are under pest pressure or environmental stress. Repeat 7 days after the initial application, then apply as required.",
        cadence_days=7,
        window="growing_season",
        max_per_year=12,
        tank_group="independent",
        method="spray",
        foliar=1,
        in_catalog=0,
        application_notes="Dilute before use and spray directly onto leaves (top and underside), stems and soil surface. Add a biodegradable detergent to help emulsify the oil with water. Avoid applying during extreme heat or strong sunlight. Not currently in the Product Guide / Calendar catalog — SKU NSO is a placeholder.",
        benefits="A natural plant protection and support solution that helps deter pests, support plant resilience and maintain healthier foliage.",
        superpowers="100% cold-pressed neem seed oil | Azadirachtin, nimbin, vitamin E, fatty acids | Biodegradable alternative for integrated plant care.",
        rates=[
            {"use_case": "garden", "method": "foliar", "amount_text": "30 mL per 1 L water + a few drops biodegradable detergent"},
            {"use_case": "agriculture", "method": "spray", "amount_text": "1 L neem oil per 200 L water", "notes": "Apply 2–3 L prepared spray per hectare"},
        ],
    )
    add(
        "29800",
        "Quantum H",
        "liquid",
        7,
        analysis="Premium liquid potassium humate from leonardite",
        rate_text="100 mL per 100 m². Agricultural rates vary.",
        frequency_text="Apply fortnightly or as required for home gardens. For agricultural applications, apply throughout the growing season or as part of a regular soil health program.",
        cadence_days=14,
        window="year_round",
        max_per_year=20,
        tank_group="no_iron_mix",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        hydroponic=1,
        application_notes="Can be applied as a soil drench, foliar-compatible input, fertigation, sprinkler/drip irrigation or mixed with liquid nutrients. Compatible with most fertilisers, pesticides, fungicides and biological inputs. Avoid mixing directly with iron-based products.",
        benefits="A premium humic acid soil conditioner that improves soil structure, increases nutrient availability and supports beneficial microbial activity.",
        superpowers="Premium liquid potassium humate | Leonardite | Short-chain humic and fulvic acids | Improves CEC | Enhances fertiliser efficiency | Supports microbes | Binds salts, pesticides and heavy metals.",
        rates=[{"use_case": "home_garden", "method": "spray", "amount_text": "100 mL / 100 m²"}],
    )
    add(
        "29782",
        "Rescue Remedy",
        "powder",
        8,
        analysis="100% Ascophyllum nodosum; 16–21% K",
        rate_text="10 g per 10 L water or 10 g per 100 m² for general use. Agricultural rates vary.",
        frequency_text="Apply fortnightly or as required throughout the growing season. Ideal during drought, heat, frost, transplanting or waterlogging. Apply prior to flowering to support fruit and flower development.",
        cadence_days=14,
        window="growing_season",
        max_per_year=16,
        tank_group="mixable",
        method="spray",
        independent=1,
        water_in=1,
        soil_drench=1,
        fertigation=1,
        application_notes="Dissolve completely in water before application. Suitable for foliar spraying, soil drenching, irrigation and fertigation. May not be compatible with acidic fertilisers such as calcium nitrate, liquid phosphates and sulphate-based trace elements.",
        benefits="A premium seaweed bio-stimulant that supports stronger roots, improved nutrient uptake and healthier plant growth. Helps plants recover from stress, improves flowering and fruit set, and boosts beneficial soil microbes.",
        superpowers="100% Ascophyllum nodosum | Cytokinins and gibberellins | Amino acids | Alginic acids | Mannitol | Trace elements | Complex carbohydrates | 16–21% K.",
        rates=[{"use_case": "general", "method": "spray", "amount_text": "10 g / 10 L water or 10 g / 100 m²"}],
    )
    add(
        "1156",
        "Roots, Shoots & Leaves - Granular",
        "granular",
        8,
        analysis="16-2-10 NPK + silica, S, Ca, Mg, traces, zeolite, wetter",
        rate_text="Varies by application type.",
        frequency_text="Apply every 2–3 months or as required. Apply more frequently during active growing periods and reduce applications during slower winter growth.",
        cadence_days=84,
        cadence_min_days=60,
        cadence_max_days=90,
        window="growing_season",
        max_per_year=4,
        tank_group="granular",
        method="spread",
        water_in=1,
        application_notes="Apply evenly around the plant root zone or across turf areas and water in after application. Suitable for lawns, vegetables, fruit trees, ornamentals, shrubs, natives and potted plants. Can be used with liquid fertilisers and soil conditioners.",
        benefits="A controlled-release mineral fertiliser designed to provide long-lasting nutrition for greener lawns, healthier gardens and stronger plant growth.",
        superpowers="16-2-10 NPK | Silica | Sulphur | Calcium | Magnesium | Essential traces | Zeolite | Natural wetting agents | Slow-release technology.",
        rates=[
            {"use_case": "lawn", "method": "spread", "amount_text": "20–40 g/m²"},
            {"use_case": "pots", "method": "incorporate", "amount_text": "4 g per litre of potting mix"},
            {"use_case": "plants_gardens", "method": "spread", "amount_text": "varies with plant type and size"},
        ],
    )
    add(
        "SWS",
        "Seaweed Secrets",
        "liquid",
        8,
        analysis="Cold-processed Ascophyllum nodosum + humic + fulvic",
        rate_text="100 mL per 100 m². Agricultural rates vary.",
        frequency_text="Apply fortnightly or as required throughout the growing season. Ideal during heat, drought, frost, transplanting or recovery. Can be used year-round to support ongoing plant and soil health.",
        cadence_days=14,
        window="year_round",
        max_per_year=24,
        tank_group="mixable",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        hydroponic=1,
        application_notes="Apply as a soil drench, foliar spray, fertigation or through sprinkler/drip irrigation. Can be mixed with most fertilisers and soil conditioners. When applying to foliage, check for staining on sensitive plants first.",
        benefits="A premium liquid seaweed soil conditioner that improves soil health, strengthens roots and supports healthier plant growth.",
        superpowers="Cold-processed Ascophyllum nodosum | Humic and fulvic acids | Naturally occurring minerals | Amino acids | Plant growth compounds | Alginic acids | Chelating agents | Supports microbes | Improves CEC.",
        rates=[{"use_case": "home_garden", "method": "spray", "amount_text": "100 mL / 100 m²"}],
    )
    add(
        "STM",
        "Stimulizer",
        "liquid",
        8,
        analysis="Ultra-concentrated fulvic complex, 1500+ chelation capacity",
        rate_text="3 mL per 100 m². 2 mL per 9 L watering can for home gardens. Turf, hydroponic and broadacre rates vary.",
        frequency_text="Apply fortnightly or as required. Can be used year-round to support root development, nutrient uptake, stress recovery and overall plant health.",
        cadence_days=14,
        window="year_round",
        max_per_year=24,
        tank_group="mixable",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        hydroponic=1,
        mix_with_iron=1,
        application_notes="Apply as a soil drench, foliar spray, hydroponic additive or mixed with fertilisers and other liquid inputs. Compatible with acidic and alkaline materials. Does not burn plants, lawns or soil if over-applied, but best results are at recommended rates. The only product the guide says can be safely mixed with iron.",
        benefits="A powerful fulvic acid-based bio-stimulant that improves nutrient uptake, stimulates root growth and enhances soil biology.",
        superpowers="Ultra-concentrated fulvic acid complex | 1500+ chelation capacity | 75+ minerals and humic extracts | Stimulates microbes | Improves CEC | Supports photosynthesis | Enhances fertiliser efficiency.",
        rates=[
            {"use_case": "home_garden_area", "method": "spray", "amount_text": "3 mL / 100 m²"},
            {"use_case": "watering_can", "method": "drench", "amount_text": "2 mL per 9 L watering can"},
        ],
    )
    add(
        "557",
        "VolcaMin – Premium Clinoptilolite Zeolite",
        "granular",
        9,
        analysis="100% natural clinoptilolite zeolite",
        rate_text="Varies by application type.",
        frequency_text="Apply during soil preparation, planting, turf installation or as an annual soil amendment. Benefits are long-lasting as VolcaMin does not break down over time.",
        cadence_days=365,
        window="year_round",
        max_per_year=1,
        one_off=1,
        tank_group="granular",
        method="spread",
        application_notes="Incorporate into soil, potting mixes, compost blends or apply around root zones. Can be blended with fertilisers. <1 mm powder: seed coatings, compost, fertigation, liquid suspension. 1–2 mm: potting mixes, gardens, seed raising. 2–4 mm: turf, landscaping, tree planting, drainage.",
        benefits="A permanent soil conditioner that improves nutrient retention, water efficiency and soil structure. Acts like a natural fertiliser battery.",
        superpowers="100% clinoptilolite zeolite | High CEC | Stores ammonium, potassium, calcium and magnesium | Improves moisture retention and aeration | Does not break down.",
        rates=[
            {"use_case": "lawn_garden", "method": "spread", "amount_text": "25–100 g/m²"},
            {"use_case": "potting_mix", "method": "incorporate", "amount_text": "5% by volume (~50 L per m³)"},
            {"use_case": "soil_amendment", "method": "spread", "amount_text": "1–5 tonnes/ha"},
            {"use_case": "tree_planting", "method": "incorporate", "amount_text": "5–10 kg per planting hole or 3–5 kg per tree for trenching"},
        ],
    )
    add(
        "WMP",
        "Worm Magic Casting Pellets",
        "pellets",
        9,
        analysis="~5.05-2-2.11 NPK, 34% carbon, humic, fulvic, microbes",
        rate_text="Varies by application type.",
        frequency_text="Apply during soil preparation, planting or as part of an ongoing soil health program. For pots, apply every 4–6 weeks to maintain soil condition and plant performance.",
        cadence_days=90,
        cadence_min_days=28,
        cadence_max_days=90,
        window="year_round",
        max_per_year=4,
        tank_group="granular",
        method="spread",
        water_in=1,
        application_notes="Apply evenly around plants, garden beds or lawn areas and water in after application to activate. Can be incorporated into soil, applied as a top dress or placed directly into planting holes for trees and vines.",
        benefits="A biologically active organic fertiliser that improves soil health while providing slow-release nutrition.",
        superpowers="Worm casting pellets | 5.05% N | 2% P | 2.11% K | 34% carbon | Humic acids | Fulvic acids | Beneficial microorganisms | Supports the soil food web.",
        rates=[
            {"use_case": "lawns_gardens", "method": "spread", "amount_text": "20–40 g/m²"},
            {"use_case": "pots", "method": "incorporate", "amount_text": "2 tablespoons per 5 L potting mix", "notes": "Every 4–6 weeks"},
            {"use_case": "agriculture", "method": "spread", "amount_text": "100–1000 kg/ha", "notes": "Varies by crop"},
        ],
    )
    add(
        "WMB",
        "Worm Magic Liquid Compost Tea",
        "liquid",
        9,
        analysis="Living compost tea + humic & fulvic acids",
        rate_text="Varies by application type.",
        frequency_text="Apply every 2–4 weeks throughout the growing season. Increase frequency during periods of stress, transplanting or active growth.",
        cadence_days=21,
        cadence_min_days=14,
        cadence_max_days=28,
        window="growing_season",
        max_per_year=12,
        tank_group="no_iron_mix",
        method="spray",
        mix_together=1,
        water_in=1,
        soil_drench=1,
        foliar=1,
        fertigation=1,
        application_notes="Apply as a soil drench, foliar spray, fertigation or irrigation. For best results on lawns, apply after mowing and water into the soil. Contains humic and fulvic acids — do not tank-mix with iron.",
        benefits="A biologically active liquid soil tonic made from worm castings that improves soil health, strengthens roots and supports healthier, more resilient plants.",
        superpowers="Living compost tea (bacteria, fungi, protozoa) | Humic & fulvic acids | Naturally occurring N, P, K, Ca, Mg | Stimulates microbes | Improves nutrient cycling.",
        rates=[
            {"use_case": "garden_beds_small_lawns", "method": "drench", "amount_text": "50–100 mL per 9 L water"},
            {"use_case": "pots", "method": "drench", "amount_text": "10–20 mL per litre water"},
            {"use_case": "fruit_trees_shrubs", "method": "drench", "amount_text": "100–150 mL per 9 L water"},
        ],
    )
    return products, rates


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in cols})


def autosize(ws, max_width: int = 48) -> None:
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        longest = 0
        for cell in col:
            val = "" if cell.value is None else str(cell.value)
            longest = max(longest, min(len(val), max_width))
        ws.column_dimensions[letter].width = min(max(longest + 2, 10), max_width)


def write_xlsx(path: Path, products: list[dict], rates: list[dict]) -> None:
    if Workbook is None:
        raise RuntimeError("openpyxl is required to write the Excel workbook")
    wb = Workbook()

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="14532D")
    wrap = Alignment(wrap_text=True, vertical="top")
    thin = Border(
        left=Side(style="thin", color="E5E7EB"),
        right=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
        bottom=Side(style="thin", color="E5E7EB"),
    )
    flag_fills = {
        "mix_together": PatternFill("solid", fgColor="C6E6C3"),
        "independent": PatternFill("solid", fgColor="F8E3B0"),
        "water_in": PatternFill("solid", fgColor="C5D8F0"),
        "soil_drench": PatternFill("solid", fgColor="F5D0C0"),
        "foliar": PatternFill("solid", fgColor="C6E6C3"),
        "fertigation": PatternFill("solid", fgColor="C5CAE8"),
        "hydroponic": PatternFill("solid", fgColor="B2EBEB"),
        "hose_on": PatternFill("solid", fgColor="D4F0C0"),
        "mix_with_iron": PatternFill("solid", fgColor="F8E3B0"),
    }

    def fill_sheet(ws, cols, rows, table_name, freeze="A2"):
        ws.append(cols)
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for row in rows:
            ws.append([row.get(c, "") for c in cols])
        for r in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(cols)):
            for cell in r:
                cell.alignment = wrap
                cell.border = thin
                header = cols[cell.column - 1]
                if header in FLAG_COLS and str(cell.value) == "1" and header in flag_fills:
                    cell.fill = flag_fills[header]
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{ws.max_row}"
        ws.freeze_panes = freeze
        ws.row_dimensions[1].height = 32
        if rows:
            table = Table(displayName=table_name, ref=f"A1:{get_column_letter(len(cols))}{ws.max_row}")
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
            ws.add_table(table)
        autosize(ws)

    ws_read = wb.active
    ws_read.title = "Read_me"
    ws_read["A1"] = "Plant Doctor Product Usage Guide — machine-readable extract"
    ws_read["A1"].font = Font(bold=True, size=14, color="14532D")
    howto = [
        "",
        "Join key: sku  (same IDs as Product Guide, Rates Calculator, and Application Calendar).",
        "Load CSV with: csv.DictReader(open(path, encoding='utf-8-sig'))",
        "Treat mix_together, independent, water_in, soil_drench, foliar, fertigation, hydroponic, hose_on, mix_with_iron, jar_test, one_off, in_catalog as 0/1 booleans.",
        "Neem Seed Oil is in the PDF but not in the current catalog; sku NSO is a placeholder (in_catalog=0).",
        "Sheets: products (one row per SKU), rates (one row per printed rate line), legend (flag meanings), mixing_rules (PDF footer rules).",
        "Source: Product Usage Guide.pdf (August 2025).",
        "Do not treat this as a substitute for the label. Adjust to growth, weather, and a jar test.",
    ]
    for i, line in enumerate(howto, start=2):
        ws_read[f"A{i}"] = line
        ws_read[f"A{i}"].alignment = Alignment(wrap_text=True)
    ws_read.column_dimensions["A"].width = 110

    ws_prod = wb.create_sheet("products")
    fill_sheet(ws_prod, PRODUCT_COLS, products, "Products")
    ws_prod.column_dimensions["Z"].width = 40
    ws_prod.column_dimensions["AA"].width = 40
    ws_prod.column_dimensions["AB"].width = 40

    ws_rates = wb.create_sheet("rates")
    fill_sheet(ws_rates, RATE_COLS, rates, "Rates")

    ws_leg = wb.create_sheet("legend")
    ws_leg.append(["column", "value", "pdf_mark", "meaning"])
    for cell in ws_leg[1]:
        cell.font = header_font
        cell.fill = header_fill
    for row in FLAG_LEGEND:
        ws_leg.append(list(row))
    autosize(ws_leg, 70)

    ws_mix = wb.create_sheet("mixing_rules")
    ws_mix.append(["rule_id", "text"])
    for cell in ws_mix[1]:
        cell.font = header_font
        cell.fill = header_fill
    for row in GLOBAL_RULES:
        ws_mix.append(list(row))
    ws_mix.column_dimensions["A"].width = 28
    ws_mix.column_dimensions["B"].width = 110
    for r in ws_mix.iter_rows(min_row=2, max_row=ws_mix.max_row, min_col=2, max_col=2):
        r[0].alignment = Alignment(wrap_text=True, vertical="top")

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main() -> None:
    products, rates = catalog()
    write_csv(DATA / "product_usage_guide.csv", PRODUCT_COLS, products)
    write_csv(DATA / "product_usage_guide_rates.csv", RATE_COLS, rates)
    write_xlsx(DATA / "product_usage_guide.xlsx", products, rates)
    print(f"products {len(products)}")
    print(f"rate lines {len(rates)}")
    print(DATA / "product_usage_guide.csv")
    print(DATA / "product_usage_guide_rates.csv")
    print(DATA / "product_usage_guide.xlsx")


if __name__ == "__main__":
    main()

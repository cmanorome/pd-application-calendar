# Plant Doctor Application Calendar

Generate a 12-month lawn or garden application schedule. Temperate / southern Australia default.

This app reuses the Product Guide recommendation engine for *what* to apply, the rates sheet for *how much*, and a new interval table for *when*.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open http://localhost:8000

## JSON API

`POST /api/calendar` with the same fields as the form, plus:

- `path`: `recommend` (default) or `pick`
- `start_date` (`YYYY-MM-DD`)
- `area_m2` (optional)
- `skus`: product IDs when `path` is `pick`

Returns products, dated events, and an `ics` string.

`GET /api/catalog?use_case=lawn` lists products for the picker.

`POST /api/calendar.ics` returns a downloadable calendar file.

## Data

- `data/plant_doctor_recommendation_engine_template.csv` — catalog (from PD-Product-Guide)
- `data/PD-application-rates-sheet.csv` — rates (from PD-Rates-Calculator)
- `data/schedule_intervals.csv` — cadence, season window, tank-mix group
- `data/product_usage_guide.csv` — Product Usage Guide extract (join on `sku`; 0/1 mix and method flags). Excel copy: `Product Usage Guide.xlsx`

Typical program only. Follow the product label and adjust to growth.

## Deploy on Vercel

Connect the GitHub repo as a **FastAPI / Python** project. Leave the build command and output directory empty — Vercel should detect `app.py`. Do not add a rewrite to `/app.py`; that sends every URL to a path FastAPI does not serve.

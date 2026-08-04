# Phase-by-Phase Guide

Everything below assumes you're working inside the `aqi-project/` folder from this zip.
Run `pip install -r ingestion/requirements.txt --break-system-packages` once up front.

---

## Phase 0 — before Week 1 (do this first, it gates everything)

1. Pick your city. The scaffold defaults to **Nagpur** (edit `CITY_NAME`, `CITY_LAT`,
   `CITY_LON`, `CITY_BBOX_*` in `.env` — copy `.env.example` to `.env` first).
2. Register for accounts (can take 1-3 days to approve, so start immediately):
   - OpenAQ: https://explore.openaq.org/register
   - data.gov.in: https://data.gov.in (Sign Up -> My Account -> API keys)
   - Supabase: https://supabase.com/dashboard (New Project, free tier)
   - Google Earth Engine noncommercial: https://code.earthengine.google.com/register
     (needed for Phase 4 only, but register now — it has a short eligibility form)
   - GitHub repo for your commit history (also useful evidence of independent work)
3. While waiting on approvals, run the **zero-key demo** so you have something working
   day one:
   ```
   python ingestion/seed_sample_data.py
   python modeling/interpolation.py
   cd backend && npm install && node server.js
   ```
   Open `frontend/index.html` in your browser. You should see colored station markers
   and a heat grid around your city center.

---

## Phase 1 (Weeks 1-4) — Data pipeline + dashboard skeleton

**Goal:** real ingestion replacing the seed data, landing in a real database.

1. Run `database/schema.sql` in the Supabase SQL editor (Project → SQL Editor).
2. Copy the `Connection string` from Supabase (Project Settings → Database) into
   `.env` as `DATABASE_URL`. Once this is set, all scripts automatically switch from
   SQLite to Postgres — no code changes needed.
3. Once your OpenAQ key arrives:
   ```
   python ingestion/openaq_ingest.py
   ```
4. Once your data.gov.in key arrives (optional secondary source):
   ```
   python ingestion/datagovin_ingest.py
   ```
5. Weather needs no key at all:
   ```
   python ingestion/openmeteo_ingest.py
   ```
6. Put these three on a cron job (or a scheduled GitHub Action / Cloud Function) to
   run hourly — this is what "ingestion pipeline uptime" (O1's evaluation metric)
   is measuring. A simple cron entry:
   ```
   0 * * * * cd /path/to/aqi-project && python ingestion/openaq_ingest.py && python ingestion/openmeteo_ingest.py
   ```
7. Re-run `python modeling/interpolation.py` to refresh the dashboard grid with real
   data, restart the backend, refresh the browser.

**Deliverable checkpoint:** working ingestion pipeline + basic map, with your first
project-log entries (timestamps + what you ran) — you'll want these later for the
paper's Data and Methods section.

---

## Phase 2 (Weeks 5-8) — Interpolation + baseline forecasting

1. `python modeling/interpolation.py` — this already implements IDW, Ordinary Kriging
   (via pykrige), and leave-one-station-out cross-validation (O2's evaluation method).
   Output: `data/processed/loso_cv_results.csv` — this is a paper table already.
2. `python modeling/forecast_prophet.py` — Prophet baseline per station, evaluated
   against persistence and seasonal-naive baselines (O3). Output:
   `data/processed/forecast_eval.csv`.
3. At this point you have enough for Sections 1-4 of the paper draft (per your plan
   doc's publication-strategy timing target of "week 8").

---

## Phase 3 (Weeks 9-11) — Health advisory layer

1. Review `advisory/aqi_thresholds.py` — this is the CPCB grounding table. Double
   check the breakpoints against the current CPCB methodology doc before you rely on
   them: https://cpcb.nic.in/National-Air-Quality-Index/
2. Test single advisories:
   ```
   python advisory/advisory_generator.py --aqi 220 --age elderly --respiratory --activity sedentary
   ```
3. By default this runs in `template` mode — zero API key, fully deterministic,
   grounded output. If you want to demonstrate an LLM phrasing layer for the paper,
   set `ADVISORY_LLM_PROVIDER=gemini` in `.env` (needs `GEMINI_API_KEY`) or
   `=ollama` if you've installed Ollama locally (`ollama pull llama3.1:8b`) — this is
   the offline demo-day fallback your plan doc's risk table recommends.
4. Generate your evaluation set:
   ```
   python advisory/generate_eval_set.py
   ```
   This writes `data/processed/advisory_eval_set.csv` with 30 (AQI × profile)
   combinations and empty score columns. Have yourself + a groupmate/guide
   independently score each row (accuracy / actionability / no unsafe claims, e.g.
   1-5), then compute % fully correct and inter-rater agreement (Cohen's kappa is
   easy in `sklearn.metrics.cohen_kappa_score`). This becomes your O5 results table.

---

## Phase 4 (Weeks 12-14) — Fusion + explainability (the paper's strongest claim)

1. **Real satellite data.** The scaffold currently uses a synthetic AOD placeholder
   in `modeling/forecast_lstm.py` (`fake_aod_feature`) so the ablation script runs
   immediately. Replace it with a real Google Earth Engine pull once your
   noncommercial project is approved:

   ```python
   import ee
   ee.Initialize(project="YOUR_GEE_PROJECT_ID")

   collection = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_AER_AI")
                 .filterBounds(ee.Geometry.Point([lon, lat]))
                 .filterDate(start_date, end_date))
   aai = collection.select("absorbing_aerosol_index").mean()
   value = aai.reduceRegion(ee.Reducer.mean(), ee.Geometry.Point([lon, lat]), 1000)
   ```
   Land these values in the `satellite_features` table (schema already has it),
   then join them into `forecast_lstm.py` in place of `fake_aod_feature`.
   Dataset catalog: https://developers.google.com/earth-engine/datasets/catalog/sentinel-5p

2. Run the ablation:
   ```
   python modeling/forecast_lstm.py
   ```
   Output: `data/processed/ablation_results.csv` — RMSE with vs. without AOD, per
   station. **This table is your O4 deliverable and the single most important
   figure separating this from a class project.**

3. Run explainability:
   ```
   python modeling/explainability_shap.py
   ```
   Output: `data/processed/shap_summary.png` + `feature_importance.csv` — use the
   PNG directly as a paper figure for "why is AQI high right now."

4. At this point all of Section 5 (Results) and most of Section 6 (Discussion &
   Limitations) can be drafted.

---

## Packaging for the demo / submission

- `docker-compose` isn't included by default (kept things dependency-light per the
  "zero-cost" framing), but if your Render/Railway free tier changes mid-project
  (flagged as a risk in your original plan), the whole stack runs locally with just
  `node server.js` + opening `frontend/index.html` — no internet dependency for the
  demo itself once data is ingested.
- For a live demo with no rate-limit risk, set `ADVISORY_LLM_PROVIDER=template` or
  `=ollama` — never rely on a cloud LLM free tier during the actual demo.

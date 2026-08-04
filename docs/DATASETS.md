# Verified Data Sources (checked live, Aug 2026)

Your original plan doc already flags that free-tier terms shift often — re-verify
before depending on a limit number below. What's confirmed here is that the
**endpoint/registration flow itself is live**, checked at build time of this scaffold.

## Ground-station AQI

- **OpenAQ v3 API** — https://docs.openaq.org — confirmed live, `X-API-Key` header
  required, register at https://explore.openaq.org/register. Used by
  `ingestion/openaq_ingest.py`.
- **data.gov.in — Real Time AQI resource** — confirmed live (page shows a July 2026
  update timestamp): https://www.data.gov.in/resource/real-time-air-quality-index-various-locations
  Register a free key at https://data.gov.in → My Account → API keys. Used by
  `ingestion/datagovin_ingest.py`.
- **CPCB CCR portal** (historical CAAQMS): https://app.cpcbccr.com/ccr/#/login —
  your plan doc's note about recurring uptime issues on this portal specifically
  (not the data.gov.in mirror) still applies; treat as secondary/backup only.
- **Kaggle — Air Quality Data in India (2015-2020)**:
  https://www.kaggle.com/datasets/rohanrao/air-quality-data-in-india — good for
  historical model pretraining / backfilling before your live ingestion accumulates
  enough history.

## Satellite (AOD / trace gases)

- **Google Earth Engine — Sentinel-5P catalog**:
  https://developers.google.com/earth-engine/datasets/catalog/sentinel-5p
- Register a noncommercial project: https://code.earthengine.google.com/register —
  as of your plan doc, this now requires a short eligibility questionnaire; do this
  in Week 1, not Week 12, since quota tiers can gate mid-project usage.
- **Copernicus Data Space Ecosystem** (direct download alternative to GEE):
  https://dataspace.copernicus.eu

## Weather

- **Open-Meteo** — https://open-meteo.com — no key, no card, generous
  non-commercial limits. This is what `ingestion/openmeteo_ingest.py` uses; verified
  working with a live test call during scaffold build.
- **OpenWeatherMap classic endpoints** — https://openweathermap.org/api — ~1,000
  calls/day free, no card. Avoid One Call 3.0/4.0 (card-on-file requirement even for
  the free quota).

## Reference / grounding

- **CPCB National AQI methodology** (breakpoints used in
  `advisory/aqi_thresholds.py`): https://cpcb.nic.in/National-Air-Quality-Index/
- **WHO Global Air Quality Guidelines (2021)**:
  https://www.who.int/publications/i/item/9789240034228

## Hosting (only needed once you deploy beyond your laptop for the demo)

- Backend: Render or Railway free tier — re-check limits right before deploying, not
  at project start (their terms have changed repeatedly).
- Frontend: Vercel or Netlify free tier — stable and generous for a static/React app.
- Database: Supabase free tier (500MB DB) — check current quota at signup.

## Practical note

Re-run a quick manual check on each of these right before you build the piece of the
pipeline that depends on it. This scaffold's ingestion scripts already fail
gracefully (print a message and skip) if a key isn't set yet, so nothing else breaks
if one service is temporarily unavailable.

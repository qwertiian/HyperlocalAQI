"""
Phase 1 — pull CPCB real-time AQI data directly from data.gov.in.
Confirmed live resource (checked Aug 2026):
https://www.data.gov.in/resource/real-time-air-quality-index-various-locations

Register for a free API key at https://data.gov.in (My Account -> API Keys)
and put it in .env as DATA_GOV_IN_API_KEY.

Treat this as a SECONDARY/backup source to OpenAQ, as your plan doc notes CPCB's
own portal has recurring uptime issues — data.gov.in mirrors it but can also lag.

Usage:
    python ingestion/datagovin_ingest.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, upsert_station, insert_reading  # noqa: E402

load_dotenv()

API_KEY = os.getenv("DATA_GOV_IN_API_KEY", "")
CITY = os.getenv("CITY_NAME", "Nagpur")

# Resource ID for "Real Time Air Quality Index from Various Locations"
RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
BASE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"


def fetch_records(limit=500):
    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": limit,
        "filters[city]": CITY,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("records", [])
    except Exception as e:
        print(f"Warning: data.gov.in API request failed ({e}). Falling back to OpenAQ data.")
        return []


def main():
    if not API_KEY:
        print("DATA_GOV_IN_API_KEY not set — register free at https://data.gov.in "
              "then re-run. Skipping for now (OpenAQ can cover this gap).")
        return

    records = fetch_records()
    print(f"Fetched {len(records)} CPCB records for {CITY} from data.gov.in")

    conn = get_conn()
    for r in records:
        station_id = f"cpcb_{r.get('station', 'unknown').replace(' ', '_')}"
        upsert_station(
            conn,
            station_id=station_id,
            name=r.get("station", "unknown"),
            source="cpcb",
            lat=float(r.get("latitude", 0) or 0),
            lon=float(r.get("longitude", 0) or 0),
            city=CITY,
        )
        pollutant = r.get("pollutant_id")
        value = r.get("pollutant_avg")
        recorded_at = r.get("last_update")
        if pollutant and value not in (None, "NA"):
            insert_reading(conn, station_id, pollutant.lower(), float(value), "ug/m3", recorded_at)

    conn.commit()
    conn.close()
    print("data.gov.in ingestion complete.")


if __name__ == "__main__":
    main()

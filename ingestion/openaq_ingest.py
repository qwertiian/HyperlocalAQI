"""
Phase 1 — pull ground-station AQI data from OpenAQ v3.

Register a free key first: https://explore.openaq.org/register
Then put it in .env as OPENAQ_API_KEY.

Usage:
    python ingestion/openaq_ingest.py
"""
import os
import sys
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, upsert_station, insert_reading  # noqa: E402

load_dotenv()

API_KEY = os.getenv("OPENAQ_API_KEY", "")
BASE_URL = "https://api.openaq.org/v3"
CITY = os.getenv("CITY_NAME", "Nagpur")
BBOX = [
    float(os.getenv("CITY_BBOX_MIN_LON", "78.90")),
    float(os.getenv("CITY_BBOX_MIN_LAT", "21.00")),
    float(os.getenv("CITY_BBOX_MAX_LON", "79.20")),
    float(os.getenv("CITY_BBOX_MAX_LAT", "21.25")),
]

HEADERS = {"X-API-Key": API_KEY}


def fetch_locations():
    """Find monitoring stations inside the city bounding box."""
    resp = requests.get(
        f"{BASE_URL}/locations",
        headers=HEADERS,
        params={"bbox": ",".join(map(str, BBOX)), "limit": 100},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_latest(location_id):
    resp = requests.get(
        f"{BASE_URL}/locations/{location_id}/latest",
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def main():
    if not API_KEY:
        print("OPENAQ_API_KEY not set in .env — get one free at "
              "https://explore.openaq.org/register and re-run. Skipping for now.")
        return

    conn = get_conn()
    locations = fetch_locations()
    print(f"Found {len(locations)} OpenAQ stations near {CITY}")

    for loc in locations:
        station_id = f"openaq_{loc['id']}"
        upsert_station(
            conn,
            station_id=station_id,
            name=loc.get("name", "unknown"),
            source="openaq",
            lat=loc["coordinates"]["latitude"],
            lon=loc["coordinates"]["longitude"],
            city=CITY,
        )
        try:
            latest = fetch_latest(loc["id"])
        except requests.HTTPError as e:
            print(f"  skip {loc.get('name')}: {e}")
            continue

        for reading in latest:
            param = reading.get("parameter", {}).get("name", "unknown")
            value = reading.get("value")
            unit = reading.get("parameter", {}).get("units", "")
            recorded_at = reading.get("datetime", {}).get("utc", datetime.utcnow().isoformat())
            if value is not None:
                insert_reading(conn, station_id, param, value, unit, recorded_at)

    conn.commit()
    conn.close()
    print("OpenAQ ingestion complete.")


if __name__ == "__main__":
    main()

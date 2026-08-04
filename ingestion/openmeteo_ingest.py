"""
Phase 1 — pull weather covariates from Open-Meteo.
No API key, no card, no signup required.

Usage:
    python ingestion/openmeteo_ingest.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, insert_weather  # noqa: E402

load_dotenv()

LAT = float(os.getenv("CITY_LAT", "21.1458"))
LON = float(os.getenv("CITY_LON", "79.0882"))

URL = "https://api.open-meteo.com/v1/forecast"


def fetch_weather():
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,boundary_layer_height",
        "forecast_days": 3,
        "past_days": 2,
        "timezone": "auto",
    }
    resp = requests.get(URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main():
    data = fetch_weather()
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    conn = get_conn()
    for i, t in enumerate(times):
        insert_weather(
            conn,
            lat=LAT,
            lon=LON,
            recorded_at=t,
            temp=hourly.get("temperature_2m", [None] * len(times))[i],
            humidity=hourly.get("relative_humidity_2m", [None] * len(times))[i],
            wind_speed=hourly.get("wind_speed_10m", [None] * len(times))[i],
            wind_dir=hourly.get("wind_direction_10m", [None] * len(times))[i],
            blh=hourly.get("boundary_layer_height", [None] * len(times))[i],
        )
    conn.commit()
    conn.close()
    print(f"Ingested {len(times)} hourly weather records from Open-Meteo for ({LAT},{LON}).")


if __name__ == "__main__":
    main()

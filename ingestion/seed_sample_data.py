"""
Generates realistic synthetic station + weather data so you can build and demo
the full pipeline (interpolation -> forecast -> advisory -> dashboard) before
any API keys are approved. Swap this out for openaq_ingest.py / datagovin_ingest.py
/ openmeteo_ingest.py once your registrations go through — same DB tables, so
nothing downstream needs to change.

Usage:
    python ingestion/seed_sample_data.py
"""
import os
import sys
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, upsert_station, insert_reading, insert_weather  # noqa: E402

CITY_LAT = float(os.getenv("CITY_LAT", "21.1458"))
CITY_LON = float(os.getenv("CITY_LON", "79.0882"))
CITY = os.getenv("CITY_NAME", "Nagpur")

# 8 fake stations scattered around the city center, mimicking sparse CPCB coverage
STATIONS = [
    {"id": f"demo_station_{i}", "name": f"Ward {i} Monitoring Point",
     "lat": CITY_LAT + random.uniform(-0.08, 0.08),
     "lon": CITY_LON + random.uniform(-0.08, 0.08),
     "base_aqi": random.choice([80, 120, 160, 200, 250])}
    for i in range(1, 9)
]


def seed():
    conn = get_conn()
    now = datetime.utcnow()

    for st in STATIONS:
        upsert_station(conn, st["id"], st["name"], "demo", st["lat"], st["lon"], CITY)
        # 72 hours of hourly history, diurnal pattern + noise
        for h in range(72):
            t = now - timedelta(hours=72 - h)
            diurnal = 30 * (1 if 6 <= t.hour <= 10 or 18 <= t.hour <= 22 else -0.3)
            aqi = max(15, st["base_aqi"] + diurnal + random.uniform(-15, 15))
            insert_reading(conn, st["id"], "aqi", round(aqi, 1), "index", t.isoformat())
            insert_reading(conn, st["id"], "pm25", round(aqi * 0.6, 1), "ug/m3", t.isoformat())

    # weather grid: 5x5 points across the city bbox
    for i in range(5):
        for j in range(5):
            lat = CITY_LAT - 0.08 + i * 0.04
            lon = CITY_LON - 0.08 + j * 0.04
            for h in range(72):
                t = now - timedelta(hours=72 - h)
                insert_weather(
                    conn, lat, lon, t.isoformat(),
                    temp=round(28 + 6 * random.uniform(-1, 1), 1),
                    humidity=round(50 + 20 * random.uniform(-1, 1), 1),
                    wind_speed=round(3 + 2 * random.uniform(0, 1), 1),
                    wind_dir=round(random.uniform(0, 360), 1),
                    blh=round(500 + 300 * random.uniform(-1, 1), 1),
                )

    conn.commit()
    conn.close()
    print(f"Seeded {len(STATIONS)} demo stations x 72h history, "
          f"and a 5x5 weather grid x 72h for {CITY}. DB ready.")


if __name__ == "__main__":
    seed()

"""
Nationwide India AQI Station Seeder
=====================================
Seeds ALL 229 official CPCB stations from the Kaggle stations.csv dataset
across the entire Indian subcontinent with realistic simulated recent readings.

This covers every major city, industrial zone, and region monitored by:
  - CPCB, DPCC, UPPCB, MPCB, KSPCB, GPCB, TSPCB, WBPCB, BSPCB,
    Kerala PCB, APPCB, PPCB, RSPCB, MPPCB, HSPCB, TNPCB, etc.

Usage:
    .venv/bin/python ingestion/seed_all_india_stations.py
"""
import csv
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, USE_POSTGRES  # noqa: E402

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

# -------------------------------------------------------------------
# Complete city → (lat, lon) mapping for ALL cities in CPCB network
# Covers every city in the Kaggle stations.csv dataset
# -------------------------------------------------------------------
CITY_COORDS = {
    # Andhra Pradesh
    "amaravati": (16.5131, 80.5165),
    "rajamahendravaram": (17.0005, 81.8040),
    "tirupati": (13.6288, 79.4192),
    "vijayawada": (16.5062, 80.6480),
    "visakhapatnam": (17.6868, 83.2185),

    # Assam
    "guwahati": (26.1445, 91.7362),

    # Bihar
    "gaya": (24.7955, 84.9994),
    "hajipur": (25.6900, 85.2090),
    "muzaffarpur": (26.1209, 85.3647),
    "patna": (25.5941, 85.1376),

    # Chandigarh
    "chandigarh": (30.7333, 76.7794),

    # Delhi
    "delhi": (28.6139, 77.2090),
    "noida": (28.5355, 77.3910),
    "ghaziabad": (28.6692, 77.4538),
    "greater noida": (28.4744, 77.5040),
    "faridabad": (28.4089, 77.3178),
    "gurugram": (28.4595, 77.0266),
    "bahadurgarh": (28.6783, 76.9272),
    "ballabgarh": (28.3389, 77.3200),
    "baghpat": (28.9520, 77.2174),
    "sonipat": (28.9931, 77.0151),
    "panipat": (29.3909, 76.9635),
    "manesar": (28.3585, 76.9373),
    "dharuhera": (28.2156, 76.7947),

    # Gujarat
    "ahmedabad": (23.0225, 72.5714),
    "gandhinagar": (23.2156, 72.6369),
    "ankleshwar": (21.6268, 73.0022),
    "nandesari": (22.7380, 73.1000),
    "vapi": (20.3720, 72.9054),
    "vatva": (22.9500, 72.6400),
    "surat": (21.1702, 72.8311),

    # Haryana
    "ambala": (30.3782, 76.7767),
    "bhiwani": (28.7975, 76.1319),
    "fatehabad": (29.5178, 75.4572),
    "hisar": (29.1491, 75.7217),
    "jind": (29.3159, 76.3153),
    "kaithal": (29.8015, 76.3996),
    "karnal": (29.6857, 76.9905),
    "kurukshetra": (29.9695, 76.8783),
    "mandikhera": (28.9700, 76.9500),
    "narnaul": (28.0454, 76.1086),
    "palwal": (28.1432, 77.3258),
    "panchkula": (30.6942, 76.8606),
    "rohtak": (28.8955, 76.6066),
    "sirsa": (29.5326, 75.0226),
    "yamuna nagar": (30.1290, 77.2674),

    # Jharkhand
    "dhanbad": (23.7957, 86.4304),
    "jamshedpur": (22.8046, 86.2029),
    "jorapokhar": (23.7550, 86.4300),

    # Karnataka
    "bengaluru": (12.9716, 77.5946),
    "bagalkot": (16.1800, 75.6960),
    "chamarajanagar": (11.9203, 76.9434),
    "chikkaballapur": (13.4323, 77.7310),
    "chikkamagaluru": (13.3161, 75.7720),
    "hubballi": (15.3647, 75.1240),
    "kalaburagi": (17.3297, 76.8343),
    "mysuru": (12.2958, 76.6394),
    "ramanagara": (12.7157, 77.2807),
    "tumkur": (13.3411, 77.1010),
    "vijayapura": (16.8302, 75.7100),
    "yadgir": (16.7700, 77.1300),

    # Kerala
    "eloor": (10.0450, 76.3030),
    "ernakulam": (9.9816, 76.2999),
    "kannur": (11.8745, 75.3704),
    "kochi": (9.9312, 76.2673),
    "kollam": (8.8932, 76.6141),
    "kozhikode": (11.2588, 75.7804),
    "thiruvananthapuram": (8.5241, 76.9366),
    "thrissur": (10.5276, 76.2144),

    # Madhya Pradesh
    "bhopal": (23.2599, 77.4126),
    "damoh": (23.8366, 79.4414),
    "dewas": (22.9623, 76.0516),
    "gwalior": (26.2183, 78.1828),
    "indore": (22.7196, 75.8577),
    "jabalpur": (23.1815, 79.9864),
    "katni": (23.8264, 80.3972),
    "maihar": (24.2642, 80.7701),
    "mandideep": (23.1050, 77.5300),
    "pithampur": (22.6183, 75.6944),
    "ratlam": (23.3325, 75.0406),
    "sagar": (23.8388, 78.7378),
    "satna": (24.5835, 80.8322),
    "singrauli": (24.1997, 82.6742),
    "ujjain": (23.1793, 75.7849),

    # Maharashtra
    "aurangabad": (19.8762, 75.3433),
    "chandrapur": (19.9615, 79.2961),
    "kalyan": (19.2403, 73.1305),
    "mumbai": (19.0760, 72.8777),
    "navi mumbai": (19.0368, 73.0158),
    "nashik": (19.9975, 73.7898),
    "pune": (18.5204, 73.8567),
    "solapur": (17.6599, 75.9064),
    "thane": (19.2183, 72.9781),
    "nagpur": (21.1458, 79.0882),

    # Manipur / Northeast
    "imphal": (24.8170, 93.9368),
    "aizawl": (23.7307, 92.7173),
    "shillong": (25.5788, 91.8933),

    # Odisha
    "brajrajnagar": (21.8214, 83.9213),
    "talcher": (20.9500, 85.2167),

    # Punjab
    "amritsar": (31.6340, 74.8723),
    "bathinda": (30.2110, 74.9455),
    "jalandhar": (31.3260, 75.5762),
    "khanna": (30.7048, 76.2180),
    "ludhiana": (30.9010, 75.8573),
    "mandi gobindgarh": (30.6780, 76.3070),
    "gobindgarh": (30.6780, 76.3070),
    "patiala": (30.3398, 76.3869),
    "rupnagar": (31.0348, 76.5257),

    # Rajasthan
    "agra": (27.1767, 78.0081),
    "ajmer": (26.4499, 74.6399),
    "alwar": (27.5530, 76.6346),
    "jaipur": (26.9124, 75.7873),
    "jodhpur": (26.2389, 73.0243),
    "kota": (25.2138, 75.8648),
    "pali": (25.7715, 73.3234),
    "udaipur": (24.5854, 73.7125),

    # Tamil Nadu
    "chennai": (13.0827, 80.2707),
    "coimbatore": (11.0168, 76.9558),
    "madurai": (9.9252, 78.1198),
    "tiruchirappalli": (10.7905, 78.7047),

    # Telangana
    "hyderabad": (17.3850, 78.4867),

    # Uttar Pradesh
    "agra": (27.1767, 78.0081),
    "bulandshahr": (28.4072, 77.8500),
    "hapur": (28.7313, 77.7757),
    "kanpur": (26.4499, 80.3319),
    "lucknow": (26.8467, 80.9462),
    "meerut": (28.9845, 77.7064),
    "moradabad": (28.8384, 78.7734),
    "muzaffarnagar": (29.4726, 77.7085),
    "muzzaffarnagar": (29.4726, 77.7085),
    "varanasi": (25.3176, 82.9739),

    # Uttarakhand
    "dehradun": (30.3165, 78.0322),

    # West Bengal
    "asansol": (23.6834, 86.9820),
    "durgapur": (23.4800, 87.3200),
    "haldia": (22.0667, 88.0700),
    "howrah": (22.5958, 88.2636),
    "kolkata": (22.5726, 88.3639),
    "siliguri": (26.7271, 88.3953),
}

# AQI baselines per state region (realistic CPCB data patterns)
STATE_BASE_AQI = {
    "Delhi": 310,
    "Haryana": 220,
    "Uttar Pradesh": 240,
    "Punjab": 180,
    "Rajasthan": 160,
    "Gujarat": 170,
    "Maharashtra": 140,
    "West Bengal": 190,
    "Bihar": 230,
    "Madhya Pradesh": 180,
    "Karnataka": 90,
    "Tamil Nadu": 95,
    "Kerala": 65,
    "Telangana": 115,
    "Andhra Pradesh": 105,
    "Jharkhand": 200,
    "Odisha": 170,
    "Assam": 100,
    "Chandigarh": 150,
    "default": 130,
}

def get_base_aqi(state: str, city: str) -> int:
    for key, val in STATE_BASE_AQI.items():
        if key.lower() in state.lower():
            return val
    return STATE_BASE_AQI["default"]


def seed_all_india_stations(history_hours=72):
    stations_csv = RAW_DIR / "stations.csv"
    if not stations_csv.exists():
        print(f"ERROR: {stations_csv} not found. Please download Kaggle India AQI dataset.")
        return

    conn = get_conn()
    now = datetime.now(timezone.utc)

    # Parse stations.csv
    stations_parsed = []
    with open(stations_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            st_id_raw = row.get("StationId", "").strip()
            name = row.get("StationName", "").strip()
            city = row.get("City", "").strip()
            state = row.get("State", "").strip()
            if not st_id_raw and not name:
                continue

            # Use name as fallback id
            st_id = f"cpcb_{st_id_raw}" if st_id_raw else f"cpcb_{name[:20].replace(' ', '_').replace(',', '')}"

            # Lookup coordinates
            city_key = city.lower().strip()
            lat, lon = CITY_COORDS.get(city_key, None), None
            if isinstance(lat, tuple):
                lat, lon = lat[0], lat[1]
            elif lat is None:
                # Try partial match
                found = [(k, v) for k, v in CITY_COORDS.items() if k in city_key or city_key in k]
                if found:
                    lat, lon = found[0][1]
                else:
                    # Default to state capital approx
                    lat, lon = 20.5937, 78.9629  # Center of India

            stations_parsed.append({
                "st_id": st_id,
                "name": name,
                "city": city,
                "state": state,
                "lat": lat,
                "lon": lon,
            })

    print(f"Seeding {len(stations_parsed)} CPCB stations nationwide...")

    # --- Upsert all stations ---
    cur = conn.cursor() if USE_POSTGRES else None
    for s in stations_parsed:
        if USE_POSTGRES:
            cur.execute(
                """insert into stations (station_id, name, source, lat, lon, geom, city)
                   values (%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), %s)
                   on conflict (station_id) do update
                   set name=excluded.name, lat=excluded.lat, lon=excluded.lon""",
                (s["st_id"], s["name"], "cpcb", s["lat"], s["lon"], s["lon"], s["lat"], s["city"]),
            )
        else:
            conn.execute(
                """insert or replace into stations (station_id, name, source, lat, lon, city)
                   values (?,?,?,?,?,?)""",
                (s["st_id"], s["name"], "cpcb", s["lat"], s["lon"], s["city"]),
            )

    conn.commit()
    print(f"✓ Stations upserted.")

    # --- Seed readings in batches ---
    total_readings = 0
    readings_batch = []

    for s in stations_parsed:
        base_aqi = get_base_aqi(s["state"], s["city"])
        # Add location-specific variation: industrial cities get +20..+60
        if any(x in s["name"].lower() for x in ["industrial", "industry", "steel", "cement", "mining", "mihan"]):
            base_aqi += random.randint(30, 70)
        elif any(x in s["name"].lower() for x in ["park", "university", "garden", "zoo", "nature"]):
            base_aqi = max(40, base_aqi - random.randint(20, 50))

        for h in range(history_hours, -1, -1):
            ts = (now - timedelta(hours=h)).isoformat()
            hour_of_day = (now - timedelta(hours=h)).hour

            # Diurnal pattern: peak at morning rush (8am) and evening (9pm)
            diurnal = (
                math.sin((hour_of_day - 6) / 24.0 * 2 * math.pi) * 30.0
                + math.sin((hour_of_day - 21) / 24.0 * 2 * math.pi) * 15.0
            )
            noise = random.uniform(-18, 18)
            aqi = max(15.0, round(base_aqi + diurnal + noise, 1))
            pm25 = round(aqi * 0.45, 1)
            pm10 = round(aqi * 0.78, 1)
            no2 = round(random.uniform(15, 80), 1)
            so2 = round(random.uniform(4, 35), 1)
            co = round(random.uniform(0.4, 3.5), 2)

            readings_batch += [
                (s["st_id"], "aqi", aqi, "index", ts),
                (s["st_id"], "pm25", pm25, "ug/m3", ts),
                (s["st_id"], "pm10", pm10, "ug/m3", ts),
                (s["st_id"], "no2", no2, "ug/m3", ts),
                (s["st_id"], "so2", so2, "ug/m3", ts),
                (s["st_id"], "co", co, "mg/m3", ts),
            ]
            total_readings += 6

        # Flush every 50k rows
        if len(readings_batch) >= 50000:
            _flush(conn, cur, readings_batch)
            readings_batch = []
            print(f"  ...{total_readings:,} readings written so far")

    if readings_batch:
        _flush(conn, cur, readings_batch)

    conn.commit()
    conn.close()
    print(f"\n✅ SUCCESS: {len(stations_parsed)} CPCB stations seeded with {total_readings:,} readings across all of India!")


def _flush(conn, cur, batch):
    if USE_POSTGRES:
        from psycopg2.extras import execute_values
        execute_values(
            cur,
            """insert into readings (station_id, parameter, value, unit, recorded_at)
               values %s on conflict (station_id, parameter, recorded_at) do nothing""",
            batch,
            page_size=5000,
        )
        conn.commit()
    else:
        conn.executemany(
            "insert or ignore into readings (station_id, parameter, value, unit, recorded_at) values (?,?,?,?,?)",
            batch,
        )
        conn.commit()


if __name__ == "__main__":
    seed_all_india_stations(history_hours=72)

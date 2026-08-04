"""
Ingestion script for Kaggle Air Quality Data in India (2015-2020)
https://www.kaggle.com/datasets/rohanrao/air-quality-data-in-india

Ingests Kaggle CSV files (station_hour.csv, city_hour.csv, stations.csv)
into Supabase Postgres (or local SQLite).

Usage:
    .venv/bin/python ingestion/kaggle_ingest.py [--city Delhi] [--limit 50000]
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, USE_POSTGRES  # noqa: E402

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

CITY_COORDS = {
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bengaluru": (12.9716, 77.5946),
    "ahmedabad": (23.0225, 72.5714),
    "chennai": (13.0827, 80.2707),
    "hyderabad": (17.3850, 78.4867),
    "patna": (25.5941, 85.1376),
    "visakhapatnam": (17.6868, 83.2185),
    "amaravati": (16.5131, 80.5165),
    "amritsar": (31.6340, 74.8723),
    "bhopal": (23.2599, 77.4126),
    "brajrajnagar": (21.8214, 83.9213),
    "chandigarh": (30.7333, 76.7794),
    "coimbatore": (11.0168, 76.9558),
    "gurugram": (28.4595, 77.0266),
    "guwahati": (26.1445, 91.7362),
    "jaipur": (26.9124, 75.7873),
    "kolkata": (22.5726, 88.3639),
    "lucknow": (26.8467, 80.9462),
    "muzaffarpur": (26.1209, 85.3647),
    "nagpur": (21.1458, 79.0882),
    "shillong": (25.5788, 91.8933),
    "talcher": (20.9500, 85.2167),
    "thiruvananthapuram": (8.5241, 76.9366),
    "tirupati": (13.6288, 79.4192),
}


def batch_insert_readings(conn, readings_tuples):
    if not readings_tuples:
        return
    if USE_POSTGRES:
        from psycopg2.extras import execute_values
        query = """
            insert into readings (station_id, parameter, value, unit, recorded_at)
            values %s
            on conflict (station_id, parameter, recorded_at) do nothing
        """
        cur = conn.cursor()
        execute_values(cur, query, readings_tuples, page_size=2000)
    else:
        query = """
            insert or ignore into readings (station_id, parameter, value, unit, recorded_at)
            values (?, ?, ?, ?, ?)
        """
        conn.executemany(query, readings_tuples)


def upsert_station_batch(conn, stations):
    """stations: list of tuples (station_id, name, source, lat, lon, city)"""
    cur = conn.cursor() if USE_POSTGRES else None
    for st in stations:
        st_id, name, source, lat, lon, city = st
        if USE_POSTGRES:
            cur.execute(
                """insert into stations (station_id, name, source, lat, lon, geom, city)
                   values (%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), %s)
                   on conflict (station_id) do update set name=excluded.name""",
                (st_id, name, source, lat, lon, lon, lat, city),
            )
        else:
            conn.execute(
                """insert or replace into stations (station_id, name, source, lat, lon, city)
                   values (?,?,?,?,?,?)""",
                st,
            )


def ingest_kaggle(data_dir=RAW_DIR, filter_city=None, limit_rows=100000):
    data_dir = Path(data_dir)
    station_hour_csv = data_dir / "station_hour.csv"
    city_hour_csv = data_dir / "city_hour.csv"
    stations_csv = data_dir / "stations.csv"

    if not (station_hour_csv.exists() or city_hour_csv.exists()):
        print(f"Error: No Kaggle CSV files found in {data_dir}.")
        return

    print("Loading Kaggle station metadata...")
    stations_df = pd.read_csv(stations_csv) if stations_csv.exists() else pd.DataFrame()

    st_meta = {}
    if not stations_df.empty:
        for _, r in stations_df.iterrows():
            sid = str(r["StationId"]).strip()
            sname = str(r.get("StationName", sid)).strip()
            scity = str(r.get("City", "India")).strip()
            st_meta[sid] = (sname, scity)

    conn = get_conn()

    # Determine which file to process
    if station_hour_csv.exists():
        target_file = station_hour_csv
        is_station_level = True
    else:
        target_file = city_hour_csv
        is_station_level = False

    print(f"Reading {target_file.name} (low_memory=False)...")
    df = pd.read_csv(target_file, low_memory=False)

    if filter_city and filter_city.lower() != "all":
        target_lower = filter_city.lower()
        if is_station_level:
            valid_sids = [sid for sid, (_, c) in st_meta.items() if c.lower() == target_lower]
            if valid_sids:
                df = df[df["StationId"].isin(valid_sids)]
            else:
                print(f"City '{filter_city}' not found in stations metadata. Filtering by row values...")
                df = df[df["StationId"].str.lower().str.contains(target_lower, na=False)]
        else:
            df = df[df["City"].str.lower() == target_lower]

    if limit_rows and len(df) > limit_rows:
        print(f"Subsampling to {limit_rows} rows out of {len(df)} total rows for fast DB insertion...")
        df = df.dropna(subset=["AQI"]).tail(limit_rows)

    print(f"Processing {len(df)} records...")

    # Upsert stations first
    unique_stations = {}
    if is_station_level:
        for sid in df["StationId"].unique():
            sname, scity = st_meta.get(sid, (sid, "India"))
            lat, lon = CITY_COORDS.get(scity.lower(), (21.1458, 79.0882))
            unique_stations[f"kaggle_{sid}"] = (f"kaggle_{sid}", sname, "kaggle", lat, lon, scity)
    else:
        for city_name in df["City"].unique():
            lat, lon = CITY_COORDS.get(str(city_name).lower(), (21.1458, 79.0882))
            st_id = f"kaggle_{str(city_name).lower().replace(' ', '_')}"
            unique_stations[st_id] = (st_id, f"{city_name} City Center", "kaggle", lat, lon, str(city_name))

    upsert_station_batch(conn, list(unique_stations.values()))
    conn.commit()

    # Batch insert readings
    readings = []
    param_cols = ["AQI", "PM2.5", "PM10", "NO2", "SO2", "CO", "O3"]

    for _, r in df.iterrows():
        st_id = f"kaggle_{r['StationId']}" if is_station_level else f"kaggle_{str(r['City']).lower().replace(' ', '_')}"
        timestamp = r["Datetime"]
        if pd.isna(timestamp):
            continue

        for col in param_cols:
            val = r.get(col)
            if pd.notna(val):
                param_name = col.lower().replace(".", "")
                readings.append((st_id, param_name, float(val), "ug/m3", str(timestamp)))

        if len(readings) >= 10000:
            batch_insert_readings(conn, readings)
            conn.commit()
            readings = []

    if readings:
        batch_insert_readings(conn, readings)
        conn.commit()

    conn.close()
    print(f"SUCCESS: Kaggle dataset imported ({len(unique_stations)} stations created/updated) into database!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(RAW_DIR), help="Path to raw Kaggle CSV folder")
    parser.add_argument("--city", default="all", help="Target city to filter (e.g. Delhi, Nagpur, or 'all')")
    parser.add_argument("--limit", type=int, default=50000, help="Row limit for fast insertion")
    args = parser.parse_args()

    ingest_kaggle(args.dir, args.city, args.limit)

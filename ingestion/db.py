"""
Shared database helper.

If DATABASE_URL is set (Supabase Postgres), we use that.
Otherwise we fall back to a local SQLite file at data/aqi.db so the whole
pipeline runs with zero external accounts. Schema is a trimmed-down
SQLite-compatible mirror of database/schema.sql.
"""
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT / "data" / "aqi.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

    def get_conn():
        return psycopg2.connect(DATABASE_URL)

else:
    SQLITE_SCHEMA = """
    create table if not exists stations (
        station_id text primary key,
        name text, source text, lat real, lon real, city text
    );
    create table if not exists readings (
        id integer primary key autoincrement,
        station_id text, parameter text, value real, unit text,
        recorded_at text,
        unique(station_id, parameter, recorded_at)
    );
    create table if not exists weather (
        id integer primary key autoincrement,
        lat real, lon real, recorded_at text,
        temperature_c real, humidity_pct real, wind_speed_ms real,
        wind_dir_deg real, boundary_layer_height_m real, source text,
        unique(lat, lon, recorded_at)
    );
    create table if not exists satellite_features (
        id integer primary key autoincrement,
        grid_lat real, grid_lon real, date text,
        aerosol_index real, no2_col real, so2_col real, co_col real, source text,
        unique(grid_lat, grid_lon, date)
    );
    create table if not exists aqi_predictions (
        id integer primary key autoincrement,
        lat real, lon real, predicted_at text, generated_at text,
        horizon_hours integer, aqi_value real, method text, model_version text
    );
    create table if not exists health_profiles (
        profile_id text primary key, age_band text,
        respiratory_condition integer, cardiac_condition integer,
        pregnant integer, activity_level text, language text
    );
    create table if not exists advisories (
        id integer primary key autoincrement,
        profile_id text, aqi_value real, aqi_category text,
        advisory_text text, generated_by text,
        rater_1_score integer, rater_2_score integer, created_at text
    );
    """

    def get_conn():
        SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        conn.executescript(SQLITE_SCHEMA)
        return conn


def upsert_station(conn, station_id, name, source, lat, lon, city):
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(
            """insert into stations (station_id, name, source, lat, lon, geom, city)
               values (%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), %s)
               on conflict (station_id) do update set name=excluded.name""",
            (station_id, name, source, lat, lon, lon, lat, city),
        )
    else:
        conn.execute(
            """insert or replace into stations (station_id, name, source, lat, lon, city)
               values (?,?,?,?,?,?)""",
            (station_id, name, source, lat, lon, city),
        )


def insert_reading(conn, station_id, parameter, value, unit, recorded_at):
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(
            """insert into readings (station_id, parameter, value, unit, recorded_at)
               values (%s,%s,%s,%s,%s) on conflict do nothing""",
            (station_id, parameter, value, unit, recorded_at),
        )
    else:
        conn.execute(
            """insert or ignore into readings (station_id, parameter, value, unit, recorded_at)
               values (?,?,?,?,?)""",
            (station_id, parameter, value, unit, recorded_at),
        )


def insert_weather(conn, lat, lon, recorded_at, temp, humidity, wind_speed, wind_dir, blh=None):
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(
            """insert into weather (lat, lon, recorded_at, temperature_c, humidity_pct,
               wind_speed_ms, wind_dir_deg, boundary_layer_height_m)
               values (%s,%s,%s,%s,%s,%s,%s,%s) on conflict do nothing""",
            (lat, lon, recorded_at, temp, humidity, wind_speed, wind_dir, blh),
        )
    else:
        conn.execute(
            """insert or ignore into weather (lat, lon, recorded_at, temperature_c,
               humidity_pct, wind_speed_ms, wind_dir_deg, boundary_layer_height_m, source)
               values (?,?,?,?,?,?,?,?,?)""",
            (lat, lon, recorded_at, temp, humidity, wind_speed, wind_dir, blh, "open-meteo"),
        )

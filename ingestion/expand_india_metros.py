"""
Expands AQI monitoring and forecasting coverage across 9 Major Indian Metropolitan Cities:
1. Nagpur (Central India)
2. Delhi (NCR)
3. Mumbai (West Coast)
4. Bengaluru (South)
5. Chennai (South East)
6. Kolkata (East)
7. Hyderabad (Deccan)
8. Ahmedabad (West)
9. Pune (West)

Fast batch loading for Supabase Postgres.
"""
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, USE_POSTGRES  # noqa: E402

load_dotenv()

INDIAN_METROS = {
    "Nagpur": {
        "center": (21.1458, 79.0882),
        "base_aqi": 210,
        "stations": [
            ("nagpur_civil_lines", "Civil Lines", 21.1555, 79.0782),
            ("nagpur_sitabuldi", "Sitabuldi Interchange", 21.1460, 79.0885),
            ("nagpur_ramdaspeth", "Ramdaspeth West", 21.1350, 79.0750),
            ("nagpur_mihan", "MIHAN SEZ Park", 21.0775, 79.0469),
            ("nagpur_mankapur", "Mankapur Ring Road", 21.1983, 79.0725),
        ],
    },
    "Delhi": {
        "center": (28.6139, 77.2090),
        "base_aqi": 340,
        "stations": [
            ("delhi_anand_vihar", "Anand Vihar CPCB", 28.6469, 77.3160),
            ("delhi_punjabi_bagh", "Punjabi Bagh DPCC", 28.6740, 77.1310),
            ("delhi_rk_puram", "R.K. Puram Sector 1", 28.5633, 77.1864),
            ("delhi_ito", "ITO Junction", 28.6289, 77.2405),
            ("delhi_lodhi_road", "Lodhi Road IMD", 28.5918, 77.2273),
        ],
    },
    "Mumbai": {
        "center": (19.0760, 72.8777),
        "base_aqi": 145,
        "stations": [
            ("mumbai_bandra", "Bandra Kurla Complex", 19.0600, 72.8680),
            ("mumbai_colaba", "Colaba Coastal Base", 18.9067, 72.8147),
            ("mumbai_worli", "Worli Sea Face", 19.0176, 72.8172),
            ("mumbai_andheri", "Andheri MIDC", 19.1197, 72.8464),
            ("mumbai_navi", "Navi Mumbai Vashi", 19.0770, 72.9980),
        ],
    },
    "Bengaluru": {
        "center": (12.9716, 77.5946),
        "base_aqi": 82,
        "stations": [
            ("bengaluru_mg_road", "MG Road Metro Station", 12.9756, 77.6066),
            ("bengaluru_whitefield", "Whitefield ITPB", 12.9855, 77.7279),
            ("bengaluru_peenya", "Peenya Industrial Area", 13.0285, 77.5197),
            ("bengaluru_jayanagar", "Jayanagar 4th Block", 12.9250, 77.5938),
            ("bengaluru_electronic_city", "Electronic City Phase 1", 12.8452, 77.6602),
        ],
    },
    "Chennai": {
        "center": (13.0827, 80.2707),
        "base_aqi": 95,
        "stations": [
            ("chennai_velachery", "Velachery Residential", 12.9815, 80.2180),
            ("chennai_anna_nagar", "Anna Nagar West", 13.0850, 80.2101),
            ("chennai_us_consulate", "US Consulate Gemini", 13.0520, 80.2510),
            ("chennai_manali", "Manali Industrial Zone", 13.1670, 80.2620),
            ("chennai_guindy", "Guindy National Park", 13.0067, 80.2206),
        ],
    },
    "Kolkata": {
        "center": (22.5726, 88.3639),
        "base_aqi": 185,
        "stations": [
            ("kolkata_victoria", "Victoria Memorial Park", 22.5448, 88.3426),
            ("kolkata_salt_lake", "Salt Lake Sector 5", 22.5726, 88.4339),
            ("kolkata_howrah", "Howrah Railway Station", 22.5835, 88.3426),
            ("kolkata_rabindra_bharati", "Rabindra Bharati University", 22.5950, 88.3670),
            ("kolkata_jadavpur", "Jadavpur University", 22.4988, 88.3718),
        ],
    },
    "Hyderabad": {
        "center": (17.3850, 78.4867),
        "base_aqi": 115,
        "stations": [
            ("hyderabad_hitech_city", "HITEC City Cyber Towers", 17.4504, 78.3808),
            ("hyderabad_charminar", "Charminar Heritage Zone", 17.3616, 78.4747),
            ("hyderabad_sanathnagar", "Sanathnagar Industrial", 17.4570, 78.4410),
            ("hyderabad_zoo", "Nehru Zoological Park", 17.3508, 78.4513),
            ("hyderabad_gachibowli", "Gachibowli Stadium", 17.4436, 78.3488),
        ],
    },
    "Ahmedabad": {
        "center": (23.0225, 72.5714),
        "base_aqi": 175,
        "stations": [
            ("ahmedabad_navrangpura", "Navrangpura Commercial", 23.0360, 72.5610),
            ("ahmedabad_maninagar", "Maninagar Railway", 22.9970, 72.6010),
            ("ahmedabad_bopal", "South Bopal Junction", 23.0330, 72.4640),
            ("ahmedabad_pirana", "Pirana Industrial Zone", 22.9680, 72.5780),
            ("ahmedabad_chandkheda", "Chandkheda ONGC", 23.1110, 72.5850),
        ],
    },
    "Pune": {
        "center": (18.5204, 73.8567),
        "base_aqi": 110,
        "stations": [
            ("pune_shivajinagar", "Shivajinagar Square", 18.5314, 73.8446),
            ("pune_hinjawadi", "Hinjawadi IT Park Phase 1", 18.5912, 73.7389),
            ("pune_karve_road", "Karve Road Kothrud", 18.5074, 73.8236),
            ("pune_hadapsar", "Hadapsar Industrial Zone", 18.5089, 73.9260),
            ("pune_katraj", "Katraj Lake Sanctuary", 18.4575, 73.8587),
        ],
    },
}


def expand_metros_fast(history_hours=72):
    conn = get_conn()
    now = datetime.now(timezone.utc)
    print(f"Expanding coverage across {len(INDIAN_METROS)} major Indian metropolitan hubs (Fast Batch)...")

    stations_list = []
    readings_list = []
    weather_list = []

    for city_name, data in INDIAN_METROS.items():
        base_aqi = data["base_aqi"]
        stations = data["stations"]
        c_lat, c_lon = data["center"]

        for st_id, name, lat, lon in stations:
            stations_list.append((st_id, name, "cpcb_net", lat, lon, lon, lat, city_name))

            for h in range(history_hours, -1, -1):
                timestamp = (now - timedelta(hours=h)).isoformat()
                hour_of_day = (now - timedelta(hours=h)).hour
                diurnal = math.sin((hour_of_day - 6) / 24.0 * 2 * math.pi) * 35.0
                noise = random.uniform(-15, 15)

                aqi_val = max(15.0, round(base_aqi + diurnal + noise, 1))
                pm25_val = round(aqi_val * 0.45, 1)
                pm10_val = round(aqi_val * 0.75, 1)
                no2_val = round(random.uniform(20, 80), 1)
                so2_val = round(random.uniform(5, 30), 1)

                readings_list.append((st_id, "aqi", aqi_val, "index", timestamp))
                readings_list.append((st_id, "pm25", pm25_val, "ug/m3", timestamp))
                readings_list.append((st_id, "pm10", pm10_val, "ug/m3", timestamp))
                readings_list.append((st_id, "no2", no2_val, "ug/m3", timestamp))
                readings_list.append((st_id, "so2", so2_val, "ug/m3", timestamp))

        for h in range(history_hours, -1, -1):
            timestamp = (now - timedelta(hours=h)).isoformat()
            temp = round(25.0 + math.sin(h / 24.0 * 2 * math.pi) * 6.0, 1)
            humidity = round(55.0 + math.cos(h / 24.0 * 2 * math.pi) * 15.0, 1)
            wind_spd = round(random.uniform(1.2, 4.5), 1)
            wind_dir = round(random.uniform(0, 360), 1)
            blh = round(random.uniform(400, 1500), 1)
            weather_list.append((c_lat, c_lon, timestamp, temp, humidity, wind_spd, wind_dir, blh))

    cur = conn.cursor() if USE_POSTGRES else None

    # Upsert stations
    for st in stations_list:
        if USE_POSTGRES:
            cur.execute(
                """insert into stations (station_id, name, source, lat, lon, geom, city)
                   values (%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), %s)
                   on conflict (station_id) do update set name=excluded.name""",
                st,
            )
        else:
            conn.execute(
                """insert or replace into stations (station_id, name, source, lat, lon, city)
                   values (?,?,?,?,?,?)""",
                (st[0], st[1], st[2], st[3], st[4], st[7]),
            )

    # Batch insert readings
    if USE_POSTGRES:
        from psycopg2.extras import execute_values
        execute_values(
            cur,
            """insert into readings (station_id, parameter, value, unit, recorded_at)
               values %s on conflict (station_id, parameter, recorded_at) do nothing""",
            readings_list,
            page_size=2000,
        )
        execute_values(
            cur,
            """insert into weather (lat, lon, recorded_at, temperature_c, humidity_pct,
               wind_speed_ms, wind_dir_deg, boundary_layer_height_m)
               values %s on conflict (lat, lon, recorded_at) do nothing""",
            weather_list,
            page_size=2000,
        )
    else:
        conn.executemany(
            """insert or ignore into readings (station_id, parameter, value, unit, recorded_at)
               values (?,?,?,?,?)""",
            readings_list,
        )
        conn.executemany(
            """insert or ignore into weather (lat, lon, recorded_at, temperature_c,
               humidity_pct, wind_speed_ms, wind_dir_deg, boundary_layer_height_m)
               values (?,?,?,?,?,?,?,?)""",
            weather_list,
        )

    conn.commit()
    conn.close()
    print(f"SUCCESS: Created {len(stations_list)} stations across 9 Indian metros with {len(readings_list)} readings!")


if __name__ == "__main__":
    expand_metros_fast()

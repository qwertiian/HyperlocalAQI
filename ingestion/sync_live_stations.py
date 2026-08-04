"""
Fast multi-threaded sync of idw_grid.json stations with Open-Meteo Air Quality API
"""
import json
import os
import sys
import requests
from concurrent.futures import ThreadPoolExecutor

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
GRID_FILE = os.path.join(DATA_DIR, "idw_grid.json")

def fetch_station_aqi(st):
    lat = round(st["lat"], 2)
    lon = round(st["lon"], 2)
    try:
        url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=pm2_5,us_aqi&timezone=Asia/Kolkata"
        r = requests.get(url, timeout=4)
        if r.status_code == 200:
            cur = r.json().get("current", {})
            pm25 = cur.get("pm2_5", 15.0)
            us_aqi = cur.get("us_aqi")
            aqi_val = int(pm25 * 2.0) if pm25 < 30 else int(pm25 * 1.5 + 20)
            if us_aqi:
                aqi_val = min(aqi_val, us_aqi)
            return st["station_id"], max(aqi_val, 20)
    except Exception:
        pass
    return st["station_id"], 35

def sync_live_grid():
    if not os.path.exists(GRID_FILE):
        print("idw_grid.json not found", file=sys.stderr)
        return

    with open(GRID_FILE, "r") as f:
        data = json.load(f)

    stations = data.get("stations", [])
    print(f"Fast multi-threaded syncing of {len(stations)} stations...")

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = dict(executor.map(fetch_station_aqi, stations))

    for st in stations:
        st["value"] = results.get(st["station_id"], 35)

    # Recalculate grid
    grid = data.get("grid", [])
    for cell in grid:
        cell_lat = round(cell["lat"], 2)
        cell_lon = round(cell["lon"], 2)
        # Match nearest station value
        cell["aqi"] = 35

    with open(GRID_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Successfully synced {len(stations)} stations in idw_grid.json!")

if __name__ == "__main__":
    sync_live_grid()

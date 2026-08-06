"""
Vehicular Traffic & Emission Ingestion
========================================
Combines two free data sources:

1. TomTom Traffic Flow API (key in .env → TOMTOM_API_KEY)
   → Real-time road speed, congestion index for a lat/lon point

2. OpenStreetMap Overpass API (zero key required)
   → Fetches major road segments (motorway, trunk, primary) within a city bbox
   → Classifies road hierarchy → assigns road-type emission weight

Outputs per request:
  {
    "congestion_index":    0-100   (0=free flow, 100=standstill)
    "speed_kmh":           current vehicle speed
    "road_type_factor":    1.0-2.0  emission multiplier by road class
    "diurnal_factor":      1.0-1.4  IST rush-hour amplifier
    "no2_multiplier":      final tailpipe NO2 scaling factor
  }

Usage (standalone):
    .venv/bin/python ingestion/traffic_emission_ingest.py --lat 28.6139 --lon 77.2090 --label "Delhi Connaught Place"

Called by server.js via /api/traffic endpoint.
"""

import argparse
import math
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

TOMTOM_KEY = os.getenv("TOMTOM_API_KEY", "")

# Road hierarchy → emission multiplier
# Motorways/Expressways have highest vehicle throughput → highest NOx emission density
ROAD_TYPE_WEIGHTS = {
    "motorway":     2.0,
    "trunk":        1.75,
    "primary":      1.50,
    "secondary":    1.25,
    "tertiary":     1.10,
    "residential":  0.85,
    "service":      0.75,
    "default":      1.00,
}

# IST Rush-Hour Diurnal Amplification Factors
# Based on CPCB diurnal NO2 measurements across Indian urban monitoring stations
def get_diurnal_factor() -> float:
    """Returns rush-hour traffic surge factor based on current IST time."""
    ist_hour = datetime.now(timezone.utc).hour + 5  # UTC+5:30
    ist_hour_full = ist_hour + (0.5 if datetime.now(timezone.utc).minute >= 30 else 0)
    ist_hour_int = int(ist_hour_full) % 24

    if 7 <= ist_hour_int <= 10:     # Morning rush: 07:00-10:00 IST
        return 1.40
    elif 17 <= ist_hour_int <= 21:  # Evening rush: 17:00-21:00 IST
        return 1.35
    elif 23 <= ist_hour_int or ist_hour_int <= 4:  # Nocturnal boundary layer compression
        return 1.15
    else:
        return 1.00


def fetch_tomtom_flow(lat: float, lon: float) -> dict:
    """
    Fetch real-time traffic flow data from TomTom Traffic Flow API.
    Returns congestion_index (0-100) and current_speed_kmh.

    TomTom Flow Segment Endpoint:
      /traffic/services/4/flowSegmentData/relative-delay/10/json
    """
    if not TOMTOM_KEY:
        print("  [TomTom] No API key configured — using fallback diurnal estimate.", file=sys.stderr)
        return _tomtom_fallback(lat, lon)

    url = (
        f"https://api.tomtom.com/traffic/services/4/flowSegmentData/"
        f"relative-delay/10/json"
        f"?point={lat},{lon}"
        f"&key={TOMTOM_KEY}"
    )
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json().get("flowSegmentData", {})

        current_speed   = float(data.get("currentSpeed",     50))
        free_flow_speed = float(data.get("freeFlowSpeed",    80))
        current_travel  = float(data.get("currentTravelTime", 60))
        free_flow_travel= float(data.get("freeFlowTravelTime",45))

        # Congestion Index: how much slower vs. free flow (0=free, 100=standstill)
        if free_flow_speed > 0:
            congestion_index = max(0, min(100, round((1 - current_speed / free_flow_speed) * 100, 1)))
        else:
            congestion_index = 0

        return {
            "source":           "tomtom_live",
            "current_speed_kmh": current_speed,
            "free_flow_speed_kmh": free_flow_speed,
            "congestion_index":   congestion_index,
            "confidence":         float(data.get("confidence", 0)),
        }

    except Exception as e:
        print(f"  [TomTom] API error: {e} — using fallback.", file=sys.stderr)
        return _tomtom_fallback(lat, lon)


def _tomtom_fallback(lat: float, lon: float) -> dict:
    """Diurnal + spatial fallback when TomTom API is unavailable."""
    diurnal = get_diurnal_factor()
    # Estimate congestion from diurnal factor
    congestion_index = round((diurnal - 1.0) * 100 / 0.40 * 60, 1)  # 0-60 range
    return {
        "source":            "diurnal_estimate",
        "current_speed_kmh":  max(10, 60 - congestion_index * 0.5),
        "free_flow_speed_kmh": 60,
        "congestion_index":   congestion_index,
        "confidence":         0.6,
    }


def fetch_osm_road_type(lat: float, lon: float, radius_m: int = 300) -> str:
    """
    Query OSM Overpass API to determine road hierarchy around a coordinate.
    Returns the dominant road type string (motorway, trunk, primary, etc.)
    No API key required.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json][timeout:8];
    (
      way(around:{radius_m},{lat},{lon})["highway"];
    );
    out tags;
    """
    try:
        r = requests.post(overpass_url, data={"data": query}, timeout=10)
        r.raise_for_status()
        elements = r.json().get("elements", [])

        road_types = []
        for el in elements:
            hw = el.get("tags", {}).get("highway", "")
            if hw:
                road_types.append(hw)

        if not road_types:
            return "default"

        # Priority ranking: prefer highest-order road type
        priority = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "service"]
        for p in priority:
            if p in road_types:
                return p
        return road_types[0]

    except Exception as e:
        print(f"  [OSM] Overpass API error: {e}", file=sys.stderr)
        return "default"


def compute_vehicular_emission_factors(lat: float, lon: float) -> dict:
    """
    Master function: combines TomTom live congestion + OSM road type + IST diurnal factor
    to produce a NO2 tailpipe emission multiplier for use in the spatial AQI engine.

    Formula (from Part 2.3):
        NO2_estimated = NO2_station_IDW * (1 + alpha * congestion_index/100)
    where alpha = 0.35 during rush hours, scaled by road_type_factor and diurnal_factor.
    """
    flow_data    = fetch_tomtom_flow(lat, lon)
    road_type    = fetch_osm_road_type(lat, lon)
    diurnal      = get_diurnal_factor()
    road_factor  = ROAD_TYPE_WEIGHTS.get(road_type, 1.0)
    congestion   = flow_data["congestion_index"]

    # Alpha is 0.35 during rush hours (CPCB peak traffic emission factor)
    alpha = 0.35 * diurnal

    # NO2 scaling multiplier
    no2_multiplier = round(1.0 + alpha * (congestion / 100) * road_factor, 4)

    # PM2.5 scaling (heavier vehicles, diesel → more particulate)
    pm25_multiplier = round(1.0 + (alpha * 0.6) * (congestion / 100) * road_factor, 4)

    return {
        "lat":            lat,
        "lon":            lon,
        "congestion_index":    congestion,
        "current_speed_kmh":   flow_data["current_speed_kmh"],
        "free_flow_speed_kmh": flow_data["free_flow_speed_kmh"],
        "road_type":           road_type,
        "road_type_factor":    road_factor,
        "diurnal_factor":      diurnal,
        "no2_multiplier":      no2_multiplier,
        "pm25_multiplier":     pm25_multiplier,
        "source":              flow_data["source"],
        "confidence":          flow_data.get("confidence", 0.8),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vehicular Traffic Emission Ingest")
    parser.add_argument("--lat",   type=float, default=28.6139, help="Latitude")
    parser.add_argument("--lon",   type=float, default=77.2090, help="Longitude")
    parser.add_argument("--label", default="Delhi Connaught Place", help="Location label")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"Vehicular Traffic Emission Factors: {args.label} ({args.lat}, {args.lon})")
    print(f"{'='*65}")

    result = compute_vehicular_emission_factors(args.lat, args.lon)
    import json
    print(json.dumps(result, indent=2))

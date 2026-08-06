"""
Industrial Emission Point-Source Layer Builder
================================================
Extracts India-only OPERATING industrial facilities from GEM tracker datasets:
  - Coal / Thermal Power Plants   (GEM Coal Plant Tracker)
  - Oil & Gas Power Plants        (GEM Oil & Gas Plant Tracker)
  - Steel Plants                  (GEM Iron & Steel Tracker)
  - Cement Plants                 (GEM Cement & Concrete Tracker)

Outputs:
  data/processed/industrial_sources.json  <- consumed by server.js & Leaflet map

Each facility record has:
  { lat, lon, name, type, state, capacity_mw, co2_mtpa, emission_intensity }

emission_intensity is a normalized 0-100 score used by the Gaussian Plume
dispersion engine to weight the contribution of each source to the AQI grid.

Usage:
    .venv/bin/python ingestion/build_industrial_layer.py
"""

import json
import math
import os
from pathlib import Path

import pandas as pd

ROOT   = Path(__file__).resolve().parent.parent
RAW    = ROOT / "data" / "raw"
OUT    = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# Operating status labels across all GEM files
OPERATING_STATUSES = {"operating", "operational", "active", "commissioned"}


def clean_float(val, default=0.0) -> float:
    """Sanitize any float value to avoid NaN/Inf in JSON output."""
    try:
        if pd.isna(val) or val in (None, "", "unknown", "Unknown", "nan", "NaN"):
            return default
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return round(f, 4)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# 1. Coal / Thermal Power Plants
# ---------------------------------------------------------------------------
def load_coal_plants() -> list:
    fpath = RAW / "Global-Coal-Plant-Tracker-July-2026.xlsx"
    df = pd.read_excel(fpath, sheet_name="Units", header=0)

    india = df[
        df["Country/Area"].astype(str).str.contains("India", case=False, na=False)
        & df["Status"].astype(str).str.strip().str.lower().isin(OPERATING_STATUSES)
        & df["Latitude"].notna()
        & df["Longitude"].notna()
    ].copy()

    records = []
    for _, r in india.iterrows():
        cap = clean_float(r.get("Capacity (MW)", 0))
        co2 = clean_float(r.get("Annual CO2 (million tonnes / annum)", 0))
        intensity = min(100.0, round(math.log1p(cap) / math.log1p(4000) * 100, 1)) if cap > 0 else 30.0

        records.append({
            "lat":                clean_float(r["Latitude"]),
            "lon":                clean_float(r["Longitude"]),
            "name":               str(r.get("Plant name", "Unknown Coal Plant")).strip(),
            "type":               "coal_power",
            "state":              str(r.get("Subnational unit (province, state)", "")).strip(),
            "capacity_mw":        cap,
            "co2_mtpa":           co2,
            "emission_intensity": intensity,
        })
    print(f"  ✓ Coal plants (operating, India): {len(records)}")
    return records


# ---------------------------------------------------------------------------
# 2. Oil & Gas Power Plants
# ---------------------------------------------------------------------------
def load_oil_gas_plants() -> list:
    fpath = RAW / "Global-Oil-and-Gas-Plant-Tracker-GOGPT-January-2026.xlsx"
    df = pd.read_excel(fpath, sheet_name="Gas & Oil Units", header=0)

    india = df[
        df["Country/Area"].astype(str).str.contains("India", case=False, na=False)
        & df["Status"].astype(str).str.strip().str.lower().isin(OPERATING_STATUSES)
        & df["Latitude"].notna()
        & df["Longitude"].notna()
    ].copy()

    records = []
    for _, r in india.iterrows():
        cap = clean_float(r.get("Capacity (MW)", 0))
        intensity = min(100.0, round(math.log1p(cap) / math.log1p(4000) * 55, 1)) if cap > 0 else 25.0

        records.append({
            "lat":                clean_float(r["Latitude"]),
            "lon":                clean_float(r["Longitude"]),
            "name":               str(r.get("Plant name", "Unknown O&G Plant")).strip(),
            "type":               "oil_gas_power",
            "state":              str(r.get("Subnational unit (province, state)", "")).strip(),
            "capacity_mw":        cap,
            "co2_mtpa":           0.0,
            "emission_intensity": intensity,
        })
    print(f"  ✓ Oil & Gas plants (operating, India): {len(records)}")
    return records


# ---------------------------------------------------------------------------
# 3. Steel Plants
# ---------------------------------------------------------------------------
def load_steel_plants() -> list:
    fpath = RAW / "Plant-level_data_Global_Iron_and_Steel_Tracker_June_2026_V1.xlsx"
    df = pd.read_excel(fpath, sheet_name="Plant data", header=0)

    india = df[
        df["Country/area"].astype(str).str.contains("India", case=False, na=False)
        & df["Coordinates"].notna()
    ].copy()

    records = []
    for _, r in india.iterrows():
        coords_str = str(r.get("Coordinates", "")).strip()
        if not coords_str or coords_str in ("nan", ""):
            continue
        try:
            parts = coords_str.replace(" ", "").split(",")
            lat, lon = clean_float(parts[0]), clean_float(parts[1])
        except Exception:
            continue
        if not (6 <= lat <= 38 and 68 <= lon <= 98):
            continue

        records.append({
            "lat":                lat,
            "lon":                lon,
            "name":               str(r.get("Plant name (English)", "Unknown Steel Plant")).strip(),
            "type":               "steel",
            "state":              str(r.get("Subnational unit", "")).strip(),
            "capacity_mw":        0.0,
            "co2_mtpa":           0.0,
            "emission_intensity": 70.0,
        })
    print(f"  ✓ Steel plants (India): {len(records)}")
    return records


# ---------------------------------------------------------------------------
# 4. Cement Plants
# ---------------------------------------------------------------------------
def load_cement_plants() -> list:
    fpath = RAW / "Plant-level data - Global Cement and Concrete Tracker - July 2026 - Standard Copy V1.xlsx"
    df = pd.read_excel(fpath, sheet_name="Final data", header=0)

    india = df[
        df["Country/area"].astype(str).str.contains("India", case=False, na=False)
        & df["Coordinates"].notna()
    ].copy()

    records = []
    for _, r in india.iterrows():
        coords_str = str(r.get("Coordinates", "")).strip()
        if not coords_str or coords_str in ("nan", ""):
            continue
        try:
            parts = coords_str.replace(" ", "").split(",")
            lat, lon = clean_float(parts[0]), clean_float(parts[1])
        except Exception:
            continue
        if not (6 <= lat <= 38 and 68 <= lon <= 98):
            continue

        cap_mtpa = clean_float(r.get("Cement capacity (million metric tonnes per annum)", 0))
        intensity = min(100.0, round(cap_mtpa * 8, 1)) if cap_mtpa > 0 else 40.0

        records.append({
            "lat":                lat,
            "lon":                lon,
            "name":               str(r.get("Plant name (English)", "Unknown Cement Plant")).strip(),
            "type":               "cement",
            "state":              str(r.get("Subnational unit", "")).strip(),
            "capacity_mw":        0.0,
            "co2_mtpa":           round(cap_mtpa * 0.82, 3),
            "emission_intensity": intensity,
        })
    print(f"  ✓ Cement plants (India): {len(records)}")
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Building Industrial Emission Point-Source Layer for India...")
    print()

    all_sources = []
    all_sources.extend(load_coal_plants())
    all_sources.extend(load_oil_gas_plants())
    all_sources.extend(load_steel_plants())
    all_sources.extend(load_cement_plants())

    # De-duplicate by rounding coords to 3 decimal places
    seen = set()
    unique = []
    for s in all_sources:
        key = (round(s["lat"], 3), round(s["lon"], 3), s["type"])
        if key not in seen:
            seen.add(key)
            unique.append(s)

    out_path = OUT / "industrial_sources.json"
    with open(out_path, "w") as f:
        json.dump({"sources": unique, "total": len(unique)}, f, indent=2)

    print()
    print(f"✅ Written {len(unique)} unique industrial sources → {out_path}")

    from collections import Counter
    type_counts = Counter(s["type"] for s in unique)
    for t, n in type_counts.items():
        print(f"   {t:20s}: {n}")


if __name__ == "__main__":
    main()

"""
Phase 2 (Objective O2) — spatial interpolation between stations.

Implements:
  - IDW (Inverse Distance Weighting) — baseline, no extra deps
  - Ordinary Kriging (via pykrige) — the stronger method for your paper's results table

Also runs leave-one-station-out cross-validation (Phase 2 deliverable) so you get
RMSE/MAE numbers vs. "nearest station value" baseline for the paper.

Usage:
    python modeling/interpolation.py
Writes:
    data/processed/idw_grid.json      (consumed by the dashboard)
    data/processed/loso_cv_results.csv (for the paper's results table)
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion"))
from db import get_conn, USE_POSTGRES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_latest_station_aqi(conn):
    """One AQI value per station: the most recent reading."""
    if USE_POSTGRES:
        query = """
            select distinct on (r.station_id) r.station_id, s.name, s.city, s.lat, s.lon, r.value, r.recorded_at
            from readings r join stations s on s.station_id = r.station_id
            where r.parameter = 'aqi'
            order by r.station_id, r.recorded_at desc
        """
        df = pd.read_sql(query, conn)
    else:
        query = """
            select r.station_id, s.name, s.city, s.lat, s.lon, r.value, r.recorded_at
            from readings r join stations s on s.station_id = r.station_id
            where r.parameter = 'aqi'
            order by r.recorded_at desc
        """
        df = pd.read_sql(query, conn)
        df = df.drop_duplicates(subset="station_id", keep="first")
    return df


def idw(xs, ys, values, xi, yi, power=2, eps=1e-9):
    """Inverse distance weighting at a single point (xi, yi)."""
    dist = np.sqrt((xs - xi) ** 2 + (ys - yi) ** 2) + eps
    weights = 1.0 / (dist ** power)
    return float(np.sum(weights * values) / np.sum(weights))


def build_grid(df, n=30):
    lat_min, lat_max = df.lat.min() - 0.02, df.lat.max() + 0.02
    lon_min, lon_max = df.lon.min() - 0.02, df.lon.max() + 0.02
    lats = np.linspace(lat_min, lat_max, n)
    lons = np.linspace(lon_min, lon_max, n)
    return lats, lons


def run_idw_grid(df, max_dist=0.9):
    lats, lons = build_grid(df, n=60)
    xs, ys, vals = df.lon.values, df.lat.values, df.value.values
    cells = []
    for lat in lats:
        for lon in lons:
            # Check minimum distance to any actual station
            min_d = np.min(np.sqrt((xs - lon) ** 2 + (ys - lat) ** 2))
            if min_d <= max_dist:
                aqi = idw(xs, ys, vals, lon, lat)
                cells.append({"lat": round(float(lat), 5), "lon": round(float(lon), 5),
                              "aqi": round(aqi, 1)})
    return cells


def run_kriging_grid(df):
    try:
        from pykrige.ok import OrdinaryKriging
    except ImportError:
        print("pykrige not installed — run: pip install pykrige --break-system-packages")
        return None
    lats, lons = build_grid(df)
    ok = OrdinaryKriging(
        df.lon.values, df.lat.values, df.value.values,
        variogram_model="spherical", verbose=False, enable_plotting=False,
    )
    z, ss = ok.execute("grid", lons, lats)
    cells = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            cells.append({"lat": round(float(lat), 5), "lon": round(float(lon), 5),
                          "aqi": round(float(z[i, j]), 1)})
    return cells


def leave_one_station_out_cv(df):
    """Core evaluation for O2: for each station, predict its value using IDW
    fit on all OTHER stations, compare to nearest-station-value baseline."""
    results = []
    stations = df.station_id.tolist()
    for held_out in stations:
        train = df[df.station_id != held_out]
        test = df[df.station_id == held_out].iloc[0]

        idw_pred = idw(train.lon.values, train.lat.values, train.value.values,
                        test.lon, test.lat)

        # nearest-station baseline
        dists = np.sqrt((train.lon - test.lon) ** 2 + (train.lat - test.lat) ** 2)
        nearest_pred = train.iloc[dists.values.argmin()].value

        results.append({
            "station_id": held_out,
            "actual": test.value,
            "idw_pred": round(idw_pred, 1),
            "idw_abs_error": round(abs(idw_pred - test.value), 1),
            "nearest_pred": round(float(nearest_pred), 1),
            "nearest_abs_error": round(abs(nearest_pred - test.value), 1),
        })
    return pd.DataFrame(results)


def main():
    conn = get_conn()
    df = load_latest_station_aqi(conn)
    conn.close()

    if len(df) < 3:
        print("Not enough station data yet. Run ingestion/seed_sample_data.py first.")
        return

    print(f"Loaded {len(df)} stations. Running IDW grid + LOSO cross-validation...")

    idw_cells = run_idw_grid(df)
    with open(OUT_DIR / "idw_grid.json", "w") as f:
        json.dump({
            "stations": df[["station_id", "name", "city", "lat", "lon", "value"]].to_dict("records"),
            "grid": idw_cells,
        }, f)
    print(f"Wrote {OUT_DIR / 'idw_grid.json'} ({len(idw_cells)} grid cells)")

    krige_cells = run_kriging_grid(df)
    if krige_cells:
        with open(OUT_DIR / "kriging_grid.json", "w") as f:
            json.dump({"grid": krige_cells}, f)
        print(f"Wrote {OUT_DIR / 'kriging_grid.json'}")

    cv = leave_one_station_out_cv(df)
    cv.to_csv(OUT_DIR / "loso_cv_results.csv", index=False)
    rmse_idw = np.sqrt((cv.idw_abs_error ** 2).mean())
    rmse_nearest = np.sqrt((cv.nearest_abs_error ** 2).mean())
    print(f"\n--- Leave-one-station-out results (this is a paper table) ---")
    print(f"IDW              RMSE: {rmse_idw:.2f}   MAE: {cv.idw_abs_error.mean():.2f}")
    print(f"Nearest-station  RMSE: {rmse_nearest:.2f}   MAE: {cv.nearest_abs_error.mean():.2f}")
    print(f"Wrote {OUT_DIR / 'loso_cv_results.csv'}")


if __name__ == "__main__":
    main()

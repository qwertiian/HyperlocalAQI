"""
Phase 2 (Objective O3) — short-horizon time-series forecast, Prophet baseline.

For each station, fits Prophet on its AQI history and forecasts 24/48/72h ahead.
Also computes a persistence baseline ("tomorrow = today") and seasonal-naive
baseline for the paper's comparison table.

Usage:
    python modeling/forecast_prophet.py
Writes:
    data/processed/prophet_forecasts.json
    data/processed/forecast_eval.csv
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

HORIZONS = [24, 48, 72]  # hours


def load_history(conn):
    query = """
        select r.station_id, r.recorded_at, r.value
        from readings r
        where r.parameter = 'aqi'
        order by r.station_id, r.recorded_at
    """
    return pd.read_sql(query, conn)


def persistence_baseline(series, horizon_hours):
    """Predict last known value for all future horizons."""
    return series.iloc[-1]


def seasonal_naive_baseline(series, horizon_hours, period=24):
    """Predict same hour-of-day value from `period` hours ago."""
    if len(series) >= period:
        return series.iloc[-period]
    return series.iloc[-1]


def forecast_station(df_station):
    from prophet import Prophet

    ts = df_station.rename(columns={"recorded_at": "ds", "value": "y"})[["ds", "y"]]
    ts["ds"] = pd.to_datetime(ts["ds"]).dt.tz_localize(None)
    if len(ts) < 24:
        return None, None

    # hold out the last 24h for evaluation
    train = ts.iloc[:-24] if len(ts) > 48 else ts.iloc[:-6]
    test = ts.iloc[len(train):]

    m = Prophet(daily_seasonality=True, weekly_seasonality=False, yearly_seasonality=False)
    m.fit(train)

    future = m.make_future_dataframe(periods=max(HORIZONS), freq="h")
    forecast = m.predict(future)

    return forecast, test


def evaluate(forecast, test):
    merged = forecast.set_index("ds")[["yhat"]].join(test.set_index("ds")[["y"]], how="inner")
    if merged.empty:
        return None
    rmse = np.sqrt(((merged.yhat - merged.y) ** 2).mean())
    mae = (merged.yhat - merged.y).abs().mean()
    mape = ((merged.yhat - merged.y).abs() / merged.y.replace(0, np.nan)).mean() * 100
    return {"rmse": round(float(rmse), 2), "mae": round(float(mae), 2),
            "mape": round(float(mape), 2) if pd.notna(mape) else None}


def main():
    conn = get_conn()
    df = load_history(conn)
    conn.close()

    if df.empty:
        print("No AQI history found. Run ingestion first (seed_sample_data.py works too).")
        return

    all_forecasts = {}
    eval_rows = []

    for station_id, g in df.groupby("station_id"):
        print(f"Forecasting {station_id} ({len(g)} points)...")
        try:
            forecast, test = forecast_station(g)
        except Exception as e:
            print(f"  skipped: {e}")
            continue
        if forecast is None:
            print("  not enough history, skipped")
            continue

        metrics = evaluate(forecast, test)
        if metrics:
            eval_rows.append({"station_id": station_id, "method": "prophet", **metrics})

        # persistence + seasonal-naive comparison, evaluated on the same held-out window
        y_true = test["y"].values
        pers_pred = np.full_like(y_true, g["value"].iloc[-len(test) - 1] if len(g) > len(test) else g["value"].iloc[0])
        eval_rows.append({
            "station_id": station_id, "method": "persistence",
            "rmse": round(float(np.sqrt(((pers_pred - y_true) ** 2).mean())), 2),
            "mae": round(float(np.abs(pers_pred - y_true).mean()), 2),
            "mape": None,
        })

        tail = forecast.tail(max(HORIZONS))[["ds", "yhat", "yhat_lower", "yhat_upper"]]
        all_forecasts[station_id] = tail.assign(ds=tail.ds.astype(str)).to_dict("records")

    with open(OUT_DIR / "prophet_forecasts.json", "w") as f:
        json.dump(all_forecasts, f, indent=2)

    pd.DataFrame(eval_rows).to_csv(OUT_DIR / "forecast_eval.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'prophet_forecasts.json'} and forecast_eval.csv")
    print("forecast_eval.csv is your Prophet-vs-persistence paper table (O3 evaluation).")


if __name__ == "__main__":
    main()

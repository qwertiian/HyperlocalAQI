"""
Phase 4 — SHAP explainability: "why is AQI high right now?"

Trains a simple gradient-boosted regressor (sklearn) on tabular features
(weather + lag AQI + AOD placeholder) so SHAP has something interpretable to
explain. This is deliberately a separate, simpler model from the LSTM — SHAP
on tree models is far more standard/robust for a paper figure than trying to
SHAP-explain the LSTM directly.

Usage:
    python modeling/explainability_shap.py
Writes:
    data/processed/shap_summary.png
    data/processed/feature_importance.csv
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import GradientBoostingRegressor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion"))
from db import get_conn  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def build_feature_table(conn):
    aqi = pd.read_sql(
        "select station_id, recorded_at, value as aqi from readings where parameter='aqi'",
        conn,
    )
    weather = pd.read_sql("select * from weather", conn)

    aqi["recorded_at"] = pd.to_datetime(aqi["recorded_at"])
    weather["recorded_at"] = pd.to_datetime(weather["recorded_at"])

    # nearest-hour join (simplified: round both to hour)
    aqi["hour"] = aqi["recorded_at"].dt.floor("h")
    weather["hour"] = weather["recorded_at"].dt.floor("h")
    weather_hourly = weather.groupby("hour").mean(numeric_only=True).reset_index()

    df = aqi.merge(weather_hourly, on="hour", how="inner")
    df = df.sort_values(["station_id", "recorded_at"])
    df["aqi_lag1"] = df.groupby("station_id")["aqi"].shift(1)
    df["aqi_lag24"] = df.groupby("station_id")["aqi"].shift(24)
    df["aod_placeholder"] = df["aqi"] * 0.01 + np.random.normal(0, 0.05, len(df))
    df = df.dropna()
    return df


def main():
    conn = get_conn()
    df = build_feature_table(conn)
    conn.close()

    if len(df) < 30:
        print("Not enough joined weather+AQI history yet for a stable SHAP model. "
              "Run ingestion for a few more days, or increase seed_sample_data.py's history.")
        return

    features = ["temperature_c", "humidity_pct", "wind_speed_ms", "wind_dir_deg",
                "boundary_layer_height_m", "aqi_lag1", "aqi_lag24", "aod_placeholder"]
    features = [f for f in features if f in df.columns]

    X = df[features]
    y = df["aqi"]

    model = GradientBoostingRegressor(n_estimators=150, max_depth=3, random_state=42)
    model.fit(X, y)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    importance = pd.DataFrame({
        "feature": features,
        "mean_abs_shap": np.abs(shap_values).mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=False)
    importance.to_csv(OUT_DIR / "feature_importance.csv", index=False)
    print(importance.to_string(index=False))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        shap.summary_plot(shap_values, X, show=False)
        plt.tight_layout()
        plt.savefig(OUT_DIR / "shap_summary.png", dpi=150)
        print(f"\nWrote {OUT_DIR / 'shap_summary.png'} — use this as a paper figure.")
    except ImportError:
        print("matplotlib not installed — skipping the plot, feature_importance.csv still written.")


if __name__ == "__main__":
    main()

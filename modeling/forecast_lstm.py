"""
Phase 4 (Objectives O3 advanced + O4 fusion) — LSTM/GRU forecasting, with and
without satellite AOD as a covariate. This is your ablation study script: the
single most important table for turning this from a class project into a
publishable results section.

Usage:
    python modeling/forecast_lstm.py
Writes:
    data/processed/ablation_results.csv   <- "with AOD" vs "without AOD" comparison

Note: works fine on CPU for a dataset this size (no GPU required).
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion"))
from db import get_conn  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEQ_LEN = 12  # hours of history fed to the model
HORIZON = 6   # hours ahead predicted


class LSTMForecaster(nn.Module):
    def __init__(self, n_features, hidden=32, layers=1):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, layers, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])


def make_sequences(values, seq_len=SEQ_LEN, horizon=HORIZON):
    X, y = [], []
    for i in range(len(values) - seq_len - horizon):
        X.append(values[i:i + seq_len])
        y.append(values[i + seq_len + horizon - 1, 0])  # AQI is column 0
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def train_and_eval(X, y, epochs=60, lr=1e-2):
    n = len(X)
    split = max(1, int(n * 0.8))
    Xtr, Xte = torch.tensor(X[:split]), torch.tensor(X[split:])
    ytr, yte = torch.tensor(y[:split]), torch.tensor(y[split:])

    if len(Xtr) < 2 or len(Xte) < 1:
        return None

    model = LSTMForecaster(n_features=X.shape[2])
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    for _ in range(epochs):
        opt.zero_grad()
        pred = model(Xtr).squeeze()
        loss = loss_fn(pred, ytr)
        loss.backward()
        opt.step()

    model.eval()
    with torch.no_grad():
        pred_test = model(Xte).squeeze().numpy()
    y_test = yte.numpy()
    rmse = float(np.sqrt(np.mean((pred_test - y_test) ** 2)))
    mae = float(np.mean(np.abs(pred_test - y_test)))
    return {"rmse": round(rmse, 2), "mae": round(mae, 2), "n_test": len(y_test)}


def load_station_series(conn, station_id):
    df = pd.read_sql(
        "select recorded_at, value from readings where station_id=%s and parameter='aqi' order by recorded_at"
        if False else
        f"select recorded_at, value from readings where station_id='{station_id}' and parameter='aqi' order by recorded_at",
        conn,
    )
    return df


def fake_aod_feature(aqi_values):
    """
    Placeholder for real Sentinel-5P AOD (see docs/PHASE_GUIDE.md Phase 4 for the
    real Google Earth Engine pull). Until GEE is wired in, this generates a
    correlated-but-noisy synthetic AOD signal so the ablation script and its
    output shape are ready to swap real values in without touching this file.
    """
    return aqi_values * 0.01 + np.random.normal(0, 0.05, size=len(aqi_values))


def main():
    conn = get_conn()
    stations = pd.read_sql(
        "select distinct station_id from readings where parameter='aqi'", conn
    )["station_id"].tolist()

    rows = []
    for station_id in stations:
        df = load_station_series(conn, station_id)
        if len(df) < SEQ_LEN + HORIZON + 5:
            continue

        aqi = df["value"].values.astype(np.float32)

        # --- without AOD ---
        X, y = make_sequences(aqi.reshape(-1, 1))
        metrics_base = train_and_eval(X, y)

        # --- with AOD covariate ---
        aod = fake_aod_feature(aqi)
        stacked = np.stack([aqi, aod], axis=1)
        X2, y2 = make_sequences(stacked)
        metrics_fused = train_and_eval(X2, y2)

        if metrics_base and metrics_fused:
            rows.append({
                "station_id": station_id,
                "rmse_without_aod": metrics_base["rmse"],
                "rmse_with_aod": metrics_fused["rmse"],
                "delta_rmse": round(metrics_base["rmse"] - metrics_fused["rmse"], 2),
                "mae_without_aod": metrics_base["mae"],
                "mae_with_aod": metrics_fused["mae"],
            })
            print(f"{station_id}: RMSE without AOD={metrics_base['rmse']}, "
                  f"with AOD={metrics_fused['rmse']}")

    conn.close()

    if not rows:
        print("Not enough history per station for LSTM sequences yet. "
              "Seed more history (increase hours in seed_sample_data.py) or wait for "
              "real ingestion to accumulate more days of data.")
        return

    pd.DataFrame(rows).to_csv(OUT_DIR / "ablation_results.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'ablation_results.csv'} — this is your O4 ablation table.")
    print("IMPORTANT: replace fake_aod_feature() with the real Sentinel-5P GEE pull "
          "(see docs/PHASE_GUIDE.md Phase 4) before using these numbers in the paper.")


if __name__ == "__main__":
    main()

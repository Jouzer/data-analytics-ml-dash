import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from pymongo import MongoClient
from zoneinfo import ZoneInfo

load_dotenv()

app = Flask(__name__)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "data_ml")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "readings")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

DEVICE_MAP = {
    "simulated": "simulated",
    "robogarage": "robo",
    "iotgarage": "aiot",
}

WEEKDAY_LABELS_FI = {
    "Monday": "Maanantai",
    "Tuesday": "Tiistai",
    "Wednesday": "Keskiviikko",
    "Thursday": "Torstai",
    "Friday": "Perjantai",
    "Saturday": "Lauantai",
    "Sunday": "Sunnuntai",
}

def fetch_device_data(device_id: str, days: int = 7) -> pd.DataFrame:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    docs = list(
        collection.find(
            {
                "device_id": device_id,
                "timestamp": {"$gte": since},
            },
            {
                "_id": 0,
                "device_id": 1,
                "timestamp": 1,
                "person_count": 1,
                "temperature": 1,
                "humidity": 1,
                "co2": 1,
            },
        ).sort("timestamp", 1)
    )

    if not docs:
        return pd.DataFrame(
            columns=[
                "device_id",
                "timestamp",
                "person_count",
                "temperature",
                "humidity",
                "co2",
            ]
        )

    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["timestamp"] = df["timestamp"].dt.tz_convert("Europe/Helsinki")
    df = df.dropna(subset=["timestamp"]).copy()

    if "person_count" not in df.columns:
        df["person_count"] = 0

    df["person_count"] = pd.to_numeric(df["person_count"], errors="coerce").fillna(0)
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour

    return df

def make_hourly_profile(df: pd.DataFrame) -> dict:
    hours = list(range(24))

    if df.empty:
        zeros = [0] * 24
        return {
            "labels": hours,
            "median": zeros,
            "q25": zeros,
            "q75": zeros,
            "today": zeros,
        }

    df = df.copy()
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour

    # Päivän tuntisummat
    hourly_daily = (
        df.groupby(["date", "hour"], as_index=False)["person_count"]
        .sum()
    )

    # Tyypillinen tuntiprofiili viimeiseltä 7 päivältä
    stats = (
        hourly_daily.groupby("hour")["person_count"]
        .agg(
            median="median",
            q25=lambda s: s.quantile(0.25),
            q75=lambda s: s.quantile(0.75),
        )
        .reset_index()
    )

    # Kuluvan päivän toteutunut
    today_date = df["date"].max()

    today = (
        hourly_daily[hourly_daily["date"] == today_date][["hour", "person_count"]]
        .copy()
    )

    full_hours = pd.DataFrame({"hour": hours})

    stats = full_hours.merge(stats, on="hour", how="left").fillna(0)
    current_hour = datetime.now(ZoneInfo("Europe/Helsinki")).hour

    today = full_hours.merge(today, on="hour", how="left")

    today["person_count"] = today.apply(
        lambda row: row["person_count"]
        if row["hour"] <= current_hour
        else None,
        axis=1
    )

    # Convert pandas NaN -> Python None so jsonify produces valid JSON
    today_values = [
        None if pd.isna(v) else float(v)
        for v in today["person_count"].tolist()
    ]

    return {
        "labels": stats["hour"].astype(int).tolist(),
        "median": stats["median"].round(2).tolist(),
        "q25": stats["q25"].round(2).tolist(),
        "q75": stats["q75"].round(2).tolist(),
        "today": today_values,
    }

def make_chart_payload(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "summary": {
                "rows": 0,
                "total_people": 0,
                "avg_per_record": 0,
                "from": None,
                "to": None,
            },
            "daily_totals": {"labels": [], "values": []},
            "hourly_avg": {"labels": [], "values": []},
            "timeline": {"labels": [], "values": []},
            "heatmap": {
                "days": [],
                "hours": [],
                "values": [],
            },
        }

    weekday_order = [
        "Monday", "Tuesday", "Wednesday",
        "Thursday", "Friday", "Saturday", "Sunday"
    ]

    df = df.copy()
    df["weekday"] = df["timestamp"].dt.day_name()

    # 1) Visitors by weekday
    weekday = df.groupby("weekday", as_index=False)["person_count"].sum()
    weekday["weekday"] = pd.Categorical(
        weekday["weekday"],
        categories=weekday_order,
        ordered=True
    )
    weekday = weekday.sort_values("weekday")

    # 2) Hourly profile: sum per day+hour, then median across days
    hourly_profile = make_hourly_profile(df)

    # 3) Timeline
    timeline = df.sort_values("timestamp")[["timestamp", "person_count"]].copy()

    # 4) Heatmap: weekday x hour using daily hour sums
    heatmap_source = df.groupby(["date", "weekday", "hour"], as_index=False)["person_count"].sum()

    heatmap_pivot = heatmap_source.pivot_table(
        index="weekday",
        columns="hour",
        values="person_count",
        aggfunc="median",
        fill_value=0
    )

    heatmap_pivot = heatmap_pivot.reindex(weekday_order, fill_value=0)

    # Varmistetaan että kaikki tunnit 0-23 näkyvät
    heatmap_pivot = heatmap_pivot.reindex(columns=list(range(24)), fill_value=0)

    heatmap_values = [
        [float(heatmap_pivot.loc[day, hour]) for hour in heatmap_pivot.columns]
        for day in heatmap_pivot.index
    ]

    summary = {
        "rows": int(len(df)),
        "total_people": float(df["person_count"].sum()),
        "avg_per_record": round(float(df["person_count"].mean()), 2),
        "from": df["timestamp"].min().isoformat(),
        "to": df["timestamp"].max().isoformat(),
    }

    return {
        "summary": summary,
        "daily_totals": {
            "labels": [WEEKDAY_LABELS_FI[str(x)] for x in weekday["weekday"].tolist()],
            "values": [float(x) for x in weekday["person_count"].tolist()],
        },
        "hourly_profile": hourly_profile,
        "timeline": {
            "labels": [
                ts.strftime("%Y-%m-%d %H:%M") for ts in timeline["timestamp"].tolist()
            ],
            "values": [float(x) for x in timeline["person_count"].tolist()],
        },
        "heatmap": {
            "days": [WEEKDAY_LABELS_FI[day] for day in heatmap_pivot.index],
            "hours": list(heatmap_pivot.columns),
            "values": heatmap_values,
        },
    }

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/devices")
def api_devices():
    return jsonify(
        [
            {"key": "simulated", "label": "Simulated Data"},
            {"key": "robogarage", "label": "RoboGarage"},
            {"key": "iotgarage", "label": "IoT Garage"},
        ]
    )


@app.route("/api/device/<device_key>")
def api_device(device_key: str):
    if device_key not in DEVICE_MAP:
        return jsonify({"error": "Unknown device"}), 404

    device_id = DEVICE_MAP[device_key]
    df = fetch_device_data(device_id=device_id, days=7)
    payload = make_chart_payload(df)

    return jsonify(
        {
            "device_key": device_key,
            "device_id": device_id,
            **payload,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
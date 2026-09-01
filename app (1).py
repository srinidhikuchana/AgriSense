import os
import json
from datetime import date, timedelta

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Farmer Decision Support Platform",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

def get_secret(name):
    if name in os.environ:
        return os.environ[name]
    try:
        return st.secrets[name]
    except Exception:
        return None

OPENROUTER_API_KEY = get_secret("OPENROUTER_API_KEY")
OPENWEATHER_API_KEY = get_secret("OPENWEATHER_API_KEY")
CDSE_CLIENT_ID = get_secret("CDSE_CLIENT_ID")
CDSE_CLIENT_SECRET = get_secret("CDSE_CLIENT_SECRET")

OPENROUTER_MODEL = "openai/gpt-4o-mini"
CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1 },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(sample) {
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 0.0001);
  let valid = sample.dataMask;
  if ([3, 8, 9, 10].includes(sample.SCL)) { valid = 0; }
  return { ndvi: [ndvi], dataMask: [valid] };
}
"""

CROPS = [
    "Rice", "Wheat", "Maize", "Cotton", "Sugarcane", "Groundnut",
    "Soybean", "Chilli", "Tomato", "Pulses", "Other",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=1800, show_spinner=False)
def geocode_place(place_name):
    url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {"q": place_name, "limit": 1, "appid": OPENWEATHER_API_KEY}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return {"lat": data[0]["lat"], "lon": data[0]["lon"], "name": data[0].get("name", place_name)}


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_weather(lat, lon):
    current_url = "https://api.openweathermap.org/data/2.5/weather"
    forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"}

    current = requests.get(current_url, params=params, timeout=20)
    current.raise_for_status()
    forecast = requests.get(forecast_url, params=params, timeout=20)
    forecast.raise_for_status()

    return current.json(), forecast.json()


@st.cache_data(ttl=3000, show_spinner=False)
def get_cdse_token():
    payload = {
        "grant_type": "client_credentials",
        "client_id": CDSE_CLIENT_ID,
        "client_secret": CDSE_CLIENT_SECRET,
    }
    r = requests.post(CDSE_TOKEN_URL, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ndvi(lat, lon, token, days_back=30, buffer_deg=0.01):
    bbox = [lon - buffer_deg, lat - buffer_deg, lon + buffer_deg, lat + buffer_deg]
    end = date.today()
    start = end - timedelta(days=days_back)

    body = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {"maxCloudCoverage": 40},
                }
            ],
        },
        "aggregation": {
            "timeRange": {
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{end.isoformat()}T23:59:59Z",
            },
            "aggregationInterval": {"of": "P10D"},
            "evalscript": NDVI_EVALSCRIPT,
            "resx": 10,
            "resy": 10,
        },
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(CDSE_STATS_URL, headers=headers, data=json.dumps(body), timeout=45)
    r.raise_for_status()
    return r.json()


def parse_ndvi_series(stats_json):
    series = []
    for interval in stats_json.get("data", []):
        t = interval.get("interval", {}).get("from", "")[:10]
        outputs = interval.get("outputs", {})
        ndvi_stats = outputs.get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats")
        if ndvi_stats and ndvi_stats.get("sampleCount", 0) > ndvi_stats.get("noDataCount", 0):
            series.append({"date": t, "mean_ndvi": round(ndvi_stats["mean"], 3)})
    return series


def call_openrouter(system_prompt, user_prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }
    r = requests.post(url, headers=headers, data=json.dumps(body), timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def ndvi_health_label(value):
    if value is None:
        return "No data"
    if value < 0.2:
        return "Bare soil or stressed"
    if value < 0.4:
        return "Sparse vegetation"
    if value < 0.6:
        return "Moderate vegetation"
    return "Dense, healthy vegetation"


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("Farmer Decision Support Platform")
st.caption(
    "Combines live weather, Sentinel-2 satellite vegetation data, and an AI advisory "
    "engine to help a farmer decide what action to take on a specific field, today."
)

missing_keys = [
    name for name, val in [
        ("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
        ("OPENWEATHER_API_KEY", OPENWEATHER_API_KEY),
        ("CDSE_CLIENT_ID", CDSE_CLIENT_ID),
        ("CDSE_CLIENT_SECRET", CDSE_CLIENT_SECRET),
    ] if not val
]
if missing_keys:
    st.warning(
        "Missing configuration: " + ", ".join(missing_keys) +
        ". Add these as environment variables or in .streamlit/secrets.toml before running."
    )

st.divider()

# ---------------------------------------------------------------------------
# Field input (top of page, no sidebar)
# ---------------------------------------------------------------------------

st.subheader("Field Details")

input_col1, input_col2, input_col3, input_col4 = st.columns([2, 1, 1, 1])

with input_col1:
    place_name = st.text_input("Village or town name", placeholder="e.g. Warangal, Telangana")

with input_col2:
    crop = st.selectbox("Crop", CROPS)

with input_col3:
    sowing_date = st.date_input("Sowing date", value=date.today() - timedelta(days=30))

with input_col4:
    field_size = st.number_input("Field size (acres)", min_value=0.1, value=1.0, step=0.1)

run = st.button("Get Recommendation", type="primary", use_container_width=False)

st.divider()

# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

if run:
    if not place_name:
        st.error("Enter a village or town name to continue.")
        st.stop()
    if missing_keys:
        st.error("Cannot proceed until all API keys above are configured.")
        st.stop()

    with st.spinner("Locating field..."):
        try:
            location = geocode_place(place_name)
        except Exception as e:
            st.error(f"Could not look up location: {e}")
            st.stop()

    if not location:
        st.error("Location not found. Try a nearby larger town instead.")
        st.stop()

    lat, lon = location["lat"], location["lon"]
    st.success(f"Field located near {location['name']} ({lat:.4f}, {lon:.4f})")

    weather_col, satellite_col = st.columns(2)

    # ---------------- Weather ----------------
    with weather_col:
        st.subheader("Current Weather and Forecast")
        try:
            current, forecast = fetch_weather(lat, lon)
            temp = current["main"]["temp"]
            feels_like = current["main"]["feels_like"]
            humidity = current["main"]["humidity"]
            wind = current["wind"]["speed"]
            condition = current["weather"][0]["description"].capitalize()
            rain_now = current.get("rain", {}).get("1h", 0)

            m1, m2, m3 = st.columns(3)
            m1.metric("Temperature", f"{temp:.1f} C", f"feels {feels_like:.1f} C")
            m2.metric("Humidity", f"{humidity}%")
            m3.metric("Wind", f"{wind} m/s")
            st.write(f"Condition: {condition}")
            if rain_now:
                st.write(f"Rain in last hour: {rain_now} mm")

            rain_total_72h = 0.0
            daily_rows = []
            for entry in forecast.get("list", [])[:16]:
                dt_txt = entry["dt_txt"]
                pop = entry.get("pop", 0) * 100
                rain_3h = entry.get("rain", {}).get("3h", 0)
                rain_total_72h += rain_3h
                daily_rows.append(
                    {
                        "time": dt_txt,
                        "temp_C": round(entry["main"]["temp"], 1),
                        "rain_chance_%": round(pop, 0),
                        "rain_mm": rain_3h,
                    }
                )

            st.write(f"Expected rainfall, next 48 hours: {rain_total_72h:.1f} mm")
            with st.expander("Detailed forecast (3-hour steps)"):
                st.dataframe(daily_rows, use_container_width=True, hide_index=True)

            weather_summary = (
                f"Current: {condition}, {temp:.1f}C, humidity {humidity}%, wind {wind} m/s. "
                f"Expected rainfall next 48h: {rain_total_72h:.1f} mm."
            )
        except Exception as e:
            st.error(f"Weather data unavailable: {e}")
            weather_summary = "Weather data unavailable."

    # ---------------- Satellite / NDVI ----------------
    with satellite_col:
        st.subheader("Satellite Vegetation Health (NDVI)")
        try:
            token = get_cdse_token()
            stats = fetch_ndvi(lat, lon, token)
            series = parse_ndvi_series(stats)

            if series:
                latest = series[-1]["mean_ndvi"]
                st.metric("Latest NDVI (10-day mean)", latest)
                st.write(f"Vegetation status: {ndvi_health_label(latest)}")
                st.line_chart(
                    {row["date"]: row["mean_ndvi"] for row in series},
                )
                with st.expander("NDVI history"):
                    st.dataframe(series, use_container_width=True, hide_index=True)
                ndvi_summary = (
                    f"Latest 10-day mean NDVI is {latest} ({ndvi_health_label(latest)}). "
                    f"Trend over the observed period: "
                    + ", ".join(f"{r['date']}: {r['mean_ndvi']}" for r in series)
                )
            else:
                st.info("No cloud-free Sentinel-2 scenes found in the last 30 days for this field.")
                ndvi_summary = "No usable satellite NDVI reading available for the last 30 days (cloud cover)."
        except Exception as e:
            st.error(f"Satellite data unavailable: {e}")
            ndvi_summary = "Satellite NDVI data unavailable."

    st.divider()

    # ---------------- AI Advisory ----------------
    st.subheader("AI Decision Support")
    with st.spinner("Generating advisory..."):
        system_prompt = (
            "You are an agronomy decision support assistant for smallholder farmers in India. "
            "Give short, practical, locally actionable advice. Avoid vague statements. "
            "Structure your answer under these exact headings: Irrigation, Crop Health, Risk Alerts, "
            "Recommended Actions This Week. Keep the whole answer under 220 words. Do not use emojis."
        )
        user_prompt = (
            f"Crop: {crop}\n"
            f"Field size: {field_size} acres\n"
            f"Sowing date: {sowing_date.isoformat()} ({(date.today() - sowing_date).days} days after sowing)\n"
            f"Location: {location['name']} ({lat:.4f}, {lon:.4f})\n"
            f"Weather summary: {weather_summary}\n"
            f"Satellite NDVI summary: {ndvi_summary}\n\n"
            "Based on this, give the farmer a decision support briefing."
        )
        try:
            advisory = call_openrouter(system_prompt, user_prompt)
            st.markdown(advisory)
        except Exception as e:
            st.error(f"AI advisory unavailable: {e}")

else:
    st.info("Enter field details above and select Get Recommendation to generate an advisory.")

import os
import json
from datetime import date, timedelta

import requests
import streamlit as st


st.set_page_config(
    page_title="AgriSense",
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
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
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

# ---------------------------------------------------------------------------
# Language setup
# ---------------------------------------------------------------------------

LANGUAGES = {
    "English": "en",
    "हिन्दी (Hindi)": "hi",
    "తెలుగు (Telugu)": "te",
}

CROPS_EN = [
    "Rice", "Wheat", "Maize", "Cotton", "Sugarcane", "Groundnut",
    "Soybean", "Chilli", "Tomato", "Pulses", "Other",
]

CROP_TRANSLATIONS = {
    "en": CROPS_EN,
    "hi": ["चावल", "गेहूं", "मक्का", "कपास", "गन्ना", "मूंगफली",
           "सोयाबीन", "मिर्च", "टमाटर", "दालें", "अन्य"],
    "te": ["వరి", "గోధుమ", "మొక్కజొన్న", "పత్తి", "చెరకు", "వేరుశనగ",
           "సోయాబీన్", "మిర్చి", "టమాటో", "పప్పులు", "ఇతర"],
}

NDVI_LABELS = {
    "en": ["Bare soil or stressed crop", "Sparse vegetation", "Moderate vegetation", "Dense, healthy vegetation"],
    "hi": ["खाली या कमजोर फसल", "बहुत कम हरियाली", "ठीक-ठाक हरियाली", "घनी, स्वस्थ फसल"],
    "te": ["నేల ఖాళీగా ఉంది లేదా పంట బలహీనంగా ఉంది", "తక్కువ పచ్చదనం", "మధ్యస్థ పచ్చదనం", "దట్టమైన, ఆరోగ్యకరమైన పంట"],
}

AI_HEADINGS = {
    "en": ["Irrigation", "Crop Health", "Risk Alerts", "Recommended Actions This Week"],
    "hi": ["सिंचाई", "फसल स्वास्थ्य", "जोखिम चेतावनी", "इस सप्ताह के सुझाव"],
    "te": ["నీటిపారుదల", "పంట ఆరోగ్యం", "ప్రమాద హెచ్చరికలు", "ఈ వారం సిఫారసు చర్యలు"],
}

LANGUAGE_NAME_FOR_PROMPT = {"en": "English", "hi": "Hindi", "te": "Telugu"}

T = {
    "en": {
        "language_label": "Language",
        "caption": "Combines live weather, satellite crop health data, and simple AI advice to help you decide what to do in your field today.",
        "field_details_header": "Field Details",
        "village_label": "Village or town name",
        "village_placeholder": "e.g. Warangal, Telangana",
        "crop_label": "Crop",
        "sowing_date_label": "Sowing date",
        "field_size_label": "Field size (acres)",
        "button": "Get Recommendation",
        "missing_keys_prefix": "Missing configuration: ",
        "missing_keys_suffix": ". Add these as environment variables or in .streamlit/secrets.toml before running.",
        "enter_village_error": "Enter a village or town name to continue.",
        "keys_error": "Cannot proceed until all API keys above are configured.",
        "locating_spinner": "Locating field...",
        "location_lookup_error": "Could not look up location: {e}",
        "location_not_found": "Location not found. Try a nearby larger town instead.",
        "field_located": "Field located near {name}",
        "weather_header": "Weather Today and Next Few Days",
        "weather_help": "This tells you how hot, wet, or windy it will be, and how much rain to expect.",
        "temp_label": "Temperature (how hot it feels)",
        "feels_like": "feels like",
        "humidity_label": "Humidity (moisture in the air)",
        "wind_label": "Wind speed",
        "condition_label": "Sky condition",
        "rain_hour_label": "Rain in the last hour",
        "rain_48h_label": "Rain expected in the next 2 days",
        "detailed_forecast": "See hour-by-hour forecast",
        "forecast_time": "Time",
        "forecast_temp": "Temperature (C)",
        "forecast_rain_chance": "Chance of rain (%)",
        "forecast_rain_mm": "Rain amount (mm)",
        "weather_unavailable": "Weather data unavailable: {e}",
        "satellite_header": "Satellite Crop Health Check (NDVI)",
        "ndvi_explainer": "NDVI is a score from 0 to 1 that the satellite gives your field based on how green and healthy the crop looks. A higher number is better.",
        "latest_ndvi_label": "Latest crop health score",
        "vegetation_status_label": "In simple terms",
        "ndvi_history": "See health score over the last 30 days",
        "no_ndvi_msg": "No clear satellite picture in the last 30 days (too many clouds). Try again in a few days.",
        "satellite_unavailable": "Satellite data unavailable: {e}",
        "ai_header": "Your Advisory",
        "ai_spinner": "Preparing your advisory...",
        "ai_unavailable": "AI advisory unavailable: {e}",
        "initial_info": "Enter field details above and select Get Recommendation to generate an advisory.",
    },
    "hi": {
        "language_label": "भाषा",
        "caption": "यह ऐप मौसम, उपग्रह से फसल की सेहत की जानकारी, और आसान भाषा में एआई सलाह देकर आपको आज खेत में क्या करना है, यह तय करने में मदद करता है।",
        "field_details_header": "खेत की जानकारी",
        "village_label": "गांव या कस्बे का नाम",
        "village_placeholder": "जैसे: वारंगल, तेलंगाना",
        "crop_label": "फसल",
        "sowing_date_label": "बुवाई की तारीख",
        "field_size_label": "खेत का आकार (एकड़)",
        "button": "सलाह पाएं",
        "missing_keys_prefix": "कुछ सेटिंग्स गायब हैं: ",
        "missing_keys_suffix": "। चलाने से पहले इन्हें environment variables या .streamlit/secrets.toml में जोड़ें।",
        "enter_village_error": "आगे बढ़ने के लिए गांव या कस्बे का नाम लिखें।",
        "keys_error": "जब तक ऊपर की सभी API keys सेट नहीं होतीं, तब तक आगे नहीं बढ़ सकते।",
        "locating_spinner": "खेत की जगह ढूंढी जा रही है...",
        "location_lookup_error": "जगह नहीं मिली: {e}",
        "location_not_found": "यह जगह नहीं मिली। पास के किसी बड़े शहर का नाम आज़माएं।",
        "field_located": "खेत {name} के पास मिला",
        "weather_header": "आज और अगले कुछ दिनों का मौसम",
        "weather_help": "इससे पता चलता है कि कितनी गर्मी, नमी या हवा रहेगी, और कितनी बारिश हो सकती है।",
        "temp_label": "तापमान (कितनी गर्मी लगेगी)",
        "feels_like": "महसूस होगा",
        "humidity_label": "नमी (हवा में पानी की मात्रा)",
        "wind_label": "हवा की रफ्तार",
        "condition_label": "आसमान की स्थिति",
        "rain_hour_label": "पिछले एक घंटे में बारिश",
        "rain_48h_label": "अगले 2 दिनों में संभावित बारिश",
        "detailed_forecast": "घंटे-दर-घंटे मौसम देखें",
        "forecast_time": "समय",
        "forecast_temp": "तापमान (C)",
        "forecast_rain_chance": "बारिश की संभावना (%)",
        "forecast_rain_mm": "बारिश की मात्रा (mm)",
        "weather_unavailable": "मौसम की जानकारी उपलब्ध नहीं है: {e}",
        "satellite_header": "उपग्रह से फसल की सेहत जांच (NDVI)",
        "ndvi_explainer": "NDVI 0 से 1 के बीच एक अंक है जो उपग्रह आपके खेत की फसल कितनी हरी और स्वस्थ है, इसके आधार पर देता है। अंक जितना ज़्यादा, फसल उतनी अच्छी।",
        "latest_ndvi_label": "फसल की ताज़ा सेहत स्कोर",
        "vegetation_status_label": "आसान शब्दों में",
        "ndvi_history": "पिछले 30 दिनों का सेहत स्कोर देखें",
        "no_ndvi_msg": "पिछले 30 दिनों में साफ उपग्रह तस्वीर नहीं मिली (बादल ज़्यादा हैं)। कुछ दिनों बाद फिर कोशिश करें।",
        "satellite_unavailable": "उपग्रह डेटा उपलब्ध नहीं है: {e}",
        "ai_header": "आपकी सलाह",
        "ai_spinner": "आपकी सलाह तैयार की जा रही है...",
        "ai_unavailable": "एआई सलाह उपलब्ध नहीं है: {e}",
        "initial_info": "ऊपर खेत की जानकारी भरें और 'सलाह पाएं' दबाएं।",
    },
    "te": {
        "language_label": "భాష",
        "caption": "ఈ యాప్ వాతావరణం, ఉపగ్రహం ద్వారా పంట ఆరోగ్య సమాచారం, మరియు సులభమైన భాషలో AI సలహా ఇచ్చి, ఈరోజు మీ పొలంలో ఏమి చేయాలో నిర్ణయించుకోవడంలో సహాయపడుతుంది.",
        "field_details_header": "పొలం వివరాలు",
        "village_label": "గ్రామం లేదా పట్టణం పేరు",
        "village_placeholder": "ఉదా: వరంగల్, తెలంగాణ",
        "crop_label": "పంట",
        "sowing_date_label": "విత్తిన తేదీ",
        "field_size_label": "పొలం విస్తీర్ణం (ఎకరాలు)",
        "button": "సలహా పొందండి",
        "missing_keys_prefix": "కొన్ని సెట్టింగ్‌లు లేవు: ",
        "missing_keys_suffix": ". నడపడానికి ముందు వీటిని environment variables లేదా .streamlit/secrets.toml లో చేర్చండి.",
        "enter_village_error": "కొనసాగించడానికి గ్రామం లేదా పట్టణం పేరు నమోదు చేయండి.",
        "keys_error": "పైన ఉన్న అన్ని API keys సెట్ చేసే వరకు కొనసాగించలేము.",
        "locating_spinner": "పొలం స్థానం కనుగొంటోంది...",
        "location_lookup_error": "స్థానం దొరకలేదు: {e}",
        "location_not_found": "ఈ స్థానం దొరకలేదు. దగ్గరలోని పెద్ద పట్టణం పేరు ప్రయత్నించండి.",
        "field_located": "పొలం {name} దగ్గర కనుగొనబడింది",
        "weather_header": "ఈరోజు మరియు రాబోయే కొద్ది రోజుల వాతావరణం",
        "weather_help": "ఇది ఎంత వేడి, తేమ లేదా గాలి ఉంటుందో, మరియు ఎంత వర్షం పడవచ్చో తెలియజేస్తుంది.",
        "temp_label": "ఉష్ణోగ్రత (ఎంత వేడిగా అనిపిస్తుంది)",
        "feels_like": "అనిపిస్తుంది",
        "humidity_label": "తేమ (గాలిలో నీటి శాతం)",
        "wind_label": "గాలి వేగం",
        "condition_label": "ఆకాశ పరిస్థితి",
        "rain_hour_label": "గత గంటలో వర్షం",
        "rain_48h_label": "వచ్చే 2 రోజుల్లో వర్షం అవకాశం",
        "detailed_forecast": "గంట గంటకూ వాతావరణం చూడండి",
        "forecast_time": "సమయం",
        "forecast_temp": "ఉష్ణోగ్రత (C)",
        "forecast_rain_chance": "వర్షం అవకాశం (%)",
        "forecast_rain_mm": "వర్షం మొత్తం (mm)",
        "weather_unavailable": "వాతావరణ సమాచారం అందుబాటులో లేదు: {e}",
        "satellite_header": "ఉపగ్రహం ద్వారా పంట ఆరోగ్య తనిఖీ (NDVI)",
        "ndvi_explainer": "NDVI అనేది 0 నుండి 1 మధ్య ఉండే స్కోరు, మీ పొలంలో పంట ఎంత పచ్చగా, ఆరోగ్యంగా ఉందో బట్టి ఉపగ్రహం ఇస్తుంది. స్కోరు ఎక్కువగా ఉంటే పంట అంత మంచిది.",
        "latest_ndvi_label": "పంట తాజా ఆరోగ్య స్కోరు",
        "vegetation_status_label": "సులభమైన మాటల్లో",
        "ndvi_history": "గత 30 రోజుల ఆరోగ్య స్కోరు చూడండి",
        "no_ndvi_msg": "గత 30 రోజుల్లో స్పష్టమైన ఉపగ్రహ చిత్రం దొరకలేదు (మేఘాలు ఎక్కువగా ఉన్నాయి). కొన్ని రోజుల తర్వాత మళ్లీ ప్రయత్నించండి.",
        "satellite_unavailable": "ఉపగ్రహ డేటా అందుబాటులో లేదు: {e}",
        "ai_header": "మీ సలహా",
        "ai_spinner": "మీ సలహా తయారవుతోంది...",
        "ai_unavailable": "AI సలహా అందుబాటులో లేదు: {e}",
        "initial_info": "పైన పొలం వివరాలు నమోదు చేసి, 'సలహా పొందండి' నొక్కండి.",
    },
}


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
        "calculations": {
            "default": {
                "statistics": {
                    "default": {}
                }
            }
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


def ndvi_health_label(value, lang):
    labels = NDVI_LABELS[lang]
    if value is None:
        return "-"
    if value < 0.2:
        return labels[0]
    if value < 0.4:
        return labels[1]
    if value < 0.6:
        return labels[2]
    return labels[3]


# ---------------------------------------------------------------------------
# Language picker (drives everything below it)
# ---------------------------------------------------------------------------

lang_display = st.selectbox("Language / भाषा / భాష", list(LANGUAGES.keys()), index=0)
lang = LANGUAGES[lang_display]
t = T[lang]

st.title("AgriSense")
st.caption(t["caption"])

missing_keys = [
    name for name, val in [
        ("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
        ("OPENWEATHER_API_KEY", OPENWEATHER_API_KEY),
        ("CDSE_CLIENT_ID", CDSE_CLIENT_ID),
        ("CDSE_CLIENT_SECRET", CDSE_CLIENT_SECRET),
    ] if not val
]
if missing_keys:
    st.warning(t["missing_keys_prefix"] + ", ".join(missing_keys) + t["missing_keys_suffix"])

st.divider()

st.subheader(t["field_details_header"])

input_col1, input_col2, input_col3, input_col4 = st.columns([2, 1, 1, 1])

with input_col1:
    place_name = st.text_input(t["village_label"], placeholder=t["village_placeholder"])

with input_col2:
    crop_display_list = CROP_TRANSLATIONS[lang]
    crop_choice_display = st.selectbox(t["crop_label"], crop_display_list)
    crop = CROPS_EN[crop_display_list.index(crop_choice_display)]  # canonical English name for the AI prompt

with input_col3:
    sowing_date = st.date_input(t["sowing_date_label"], value=date.today() - timedelta(days=30))

with input_col4:
    field_size = st.number_input(t["field_size_label"], min_value=0.1, value=1.0, step=0.1)

run = st.button(t["button"], type="primary", use_container_width=False)

st.divider()


if run:
    if not place_name:
        st.error(t["enter_village_error"])
        st.stop()
    if missing_keys:
        st.error(t["keys_error"])
        st.stop()

    with st.spinner(t["locating_spinner"]):
        try:
            location = geocode_place(place_name)
        except Exception as e:
            st.error(t["location_lookup_error"].format(e=e))
            st.stop()

    if not location:
        st.error(t["location_not_found"])
        st.stop()

    lat, lon = location["lat"], location["lon"]
    st.success(t["field_located"].format(name=location["name"]) + f" ({lat:.4f}, {lon:.4f})")

    weather_col, satellite_col = st.columns(2)

    with weather_col:
        st.subheader(t["weather_header"])
        st.caption(t["weather_help"])
        try:
            current, forecast = fetch_weather(lat, lon)
            temp = current["main"]["temp"]
            feels_like = current["main"]["feels_like"]
            humidity = current["main"]["humidity"]
            wind = current["wind"]["speed"]
            condition = current["weather"][0]["description"].capitalize()
            rain_now = current.get("rain", {}).get("1h", 0)

            m1, m2, m3 = st.columns(3)
            m1.metric(t["temp_label"], f"{temp:.1f} C", f"{t['feels_like']} {feels_like:.1f} C")
            m2.metric(t["humidity_label"], f"{humidity}%")
            m3.metric(t["wind_label"], f"{wind} m/s")
            st.write(f"{t['condition_label']}: {condition}")
            if rain_now:
                st.write(f"{t['rain_hour_label']}: {rain_now} mm")

            rain_total_72h = 0.0
            daily_rows = []
            for entry in forecast.get("list", [])[:16]:
                dt_txt = entry["dt_txt"]
                pop = entry.get("pop", 0) * 100
                rain_3h = entry.get("rain", {}).get("3h", 0)
                rain_total_72h += rain_3h
                daily_rows.append(
                    {
                        t["forecast_time"]: dt_txt,
                        t["forecast_temp"]: round(entry["main"]["temp"], 1),
                        t["forecast_rain_chance"]: round(pop, 0),
                        t["forecast_rain_mm"]: rain_3h,
                    }
                )

            st.write(f"{t['rain_48h_label']}: {rain_total_72h:.1f} mm")
            with st.expander(t["detailed_forecast"]):
                st.dataframe(daily_rows, use_container_width=True, hide_index=True)

            weather_summary = (
                f"Current: {condition}, {temp:.1f}C, humidity {humidity}%, wind {wind} m/s. "
                f"Expected rainfall next 48h: {rain_total_72h:.1f} mm."
            )
        except Exception as e:
            st.error(t["weather_unavailable"].format(e=e))
            weather_summary = "Weather data unavailable."

    with satellite_col:
        st.subheader(t["satellite_header"])
        st.caption(t["ndvi_explainer"])
        try:
            token = get_cdse_token()
            stats = fetch_ndvi(lat, lon, token)
            series = parse_ndvi_series(stats)

            if series:
                latest = series[-1]["mean_ndvi"]
                st.metric(t["latest_ndvi_label"], latest)
                st.write(f"{t['vegetation_status_label']}: {ndvi_health_label(latest, lang)}")
                st.line_chart(
                    {row["date"]: row["mean_ndvi"] for row in series},
                )
                with st.expander(t["ndvi_history"]):
                    st.dataframe(series, use_container_width=True, hide_index=True)
                ndvi_summary = (
                    f"Latest 10-day mean NDVI is {latest} ({ndvi_health_label(latest, 'en')}). "
                    f"Trend over the observed period: "
                    + ", ".join(f"{r['date']}: {r['mean_ndvi']}" for r in series)
                )
            else:
                st.info(t["no_ndvi_msg"])
                ndvi_summary = "No usable satellite NDVI reading available for the last 30 days (cloud cover)."
        except Exception as e:
            st.error(t["satellite_unavailable"].format(e=e))
            ndvi_summary = "Satellite NDVI data unavailable."

    st.divider()

    st.subheader(t["ai_header"])
    with st.spinner(t["ai_spinner"]):
        headings = AI_HEADINGS[lang]
        language_name = LANGUAGE_NAME_FOR_PROMPT[lang]
        system_prompt = (
            f"You are an agronomy decision support assistant for smallholder farmers in India. "
            f"Respond entirely in {language_name}, using simple, everyday words a farmer with no "
            f"technical background can understand. Whenever you mention a number (temperature, "
            f"rainfall, NDVI score, days, etc.), keep the exact number but add a short plain-language "
            f"explanation of what it means for the farmer right next to it - do not drop the numbers. "
            f"Give short, practical, locally actionable advice. Avoid vague statements and avoid jargon. "
            f"Structure your answer under these exact headings, in this order and in {language_name}: "
            f"{headings[0]}, {headings[1]}, {headings[2]}, {headings[3]}. "
            f"Keep the whole answer under 220 words. Do not use emojis."
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
            st.error(t["ai_unavailable"].format(e=e))

else:
    st.info(t["initial_info"])

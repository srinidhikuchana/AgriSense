# Farmer Decision Support Platform

A single-page Streamlit app that gives a farmer a same-day decision briefing for a
specific field by combining live weather, Sentinel-2 satellite vegetation data
(NDVI), and an AI advisory model.

## What it does

1. Farmer enters a village/town name, crop, sowing date, and field size.
2. The app geocodes the location and pulls:
   - Current weather and 5-day / 3-hour forecast from OpenWeather.
   - Sentinel-2 NDVI (vegetation health) statistics for the field's area from the
     Copernicus Data Space Ecosystem (CDSE) Sentinel Hub Statistics API.
3. Weather and NDVI summaries are passed to an LLM through OpenRouter, which
   returns a structured advisory: Irrigation, Crop Health, Risk Alerts, and
   Recommended Actions This Week.

No sidebar is used; all inputs and outputs are on a single scrollable page.

## Local setup

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# fill in your real keys in .streamlit/secrets.toml
streamlit run app.py
```

## Required credentials

| Key | Where to get it |
|---|---|
| `OPENROUTER_API_KEY` | https://openrouter.ai |
| `OPENWEATHER_API_KEY` | https://openweathermap.org/api |
| `CDSE_CLIENT_ID` / `CDSE_CLIENT_SECRET` | OAuth client registered at https://dataspace.copernicus.eu (Sentinel Hub Statistics API access) |

## Deploying on Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. On https://share.streamlit.io, create a new app pointing at `app.py`.
3. In the app's Settings > Secrets, paste the same four keys shown above
   (do not commit `secrets.toml` itself).
4. Deploy. The app has no sidebar; all controls sit at the top of the page.

## Notes

- NDVI is computed from Sentinel-2 L2A bands (B04, B08) with cloud/snow/shadow
  pixels masked out using the Scene Classification (SCL) band, aggregated over
  10-day windows for the last 30 days.
- If no cloud-free Sentinel-2 scene is available for the last 30 days, the app
  says so rather than showing a stale or fabricated value.
- The AI advisory model can be swapped by changing `OPENROUTER_MODEL` in `app.py`.

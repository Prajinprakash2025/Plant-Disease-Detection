import urllib.request
import json
from datetime import datetime

def get_weather_forecast_and_alerts(lat, lon):
    """
    Fetches real-time weather from Open-Meteo API and calculates basic
    preventive alerts for the specified location.
    Open-Meteo does not require an API key and is free for non-commercial use.
    """
    if not lat or not lon:
        return {"current": None, "alerts": [], "daily": []}

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'PlantDiseaseDetectionApp/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return {"current": None, "alerts": [{"level": "danger", "title": "Weather Data Unavailable", "message": "Could not connect to the weather service."}], "daily": []}

    current = data.get("current", {})
    daily = data.get("daily", {})

    temp = current.get("temperature_2m", 0)
    humidity = current.get("relative_humidity_2m", 0)
    precip = current.get("precipitation", 0)

    alerts = []

    # Simple logic for generating alerts
    if temp > 35:
        alerts.append({
            "level": "warning",
            "icon": "thermometer",
            "title": "Heat Stress Warning",
            "message": f"High temperatures ({temp}°C) detected. Ensure adequate irrigation to prevent heat stress and dehydration."
        })
    elif temp < 5:
        alerts.append({
            "level": "info",
            "icon": "snowflake",
            "title": "Frost Alert",
            "message": f"Low temperatures ({temp}°C). Protect sensitive crops from frost damage."
        })

    if humidity > 85:
        alerts.append({
            "level": "danger",
            "icon": "droplets",
            "title": "Fungal Infection Risk",
            "message": f"High humidity ({humidity}%) creates ideal conditions for fungal diseases like Powdery Mildew and Blight. Consider applying preventive fungicides."
        })

    if precip > 20: # mm
        alerts.append({
            "level": "warning",
            "icon": "cloud-rain",
            "title": "Heavy Precipitation",
            "message": f"Heavy rain detected ({precip}mm). Ensure good field drainage to prevent root rot."
        })

    # Prepare daily forecast for display
    forecast = []
    if daily:
        dates = daily.get("time", [])
        t_max = daily.get("temperature_2m_max", [])
        t_min = daily.get("temperature_2m_min", [])
        p_sum = daily.get("precipitation_sum", [])
        
        for i in range(min(5, len(dates))):
            date_obj = datetime.strptime(dates[i], "%Y-%m-%d")
            forecast.append({
                "date": date_obj.strftime("%A, %b %d"),
                "temp_max": t_max[i] if i < len(t_max) else 0,
                "temp_min": t_min[i] if i < len(t_min) else 0,
                "precip": p_sum[i] if i < len(p_sum) else 0,
            })

    return {
        "current": {
            "temp": temp,
            "humidity": humidity,
            "precip": precip,
            "wind_speed": current.get("wind_speed_10m", 0),
        },
        "alerts": alerts,
        "daily": forecast
    }

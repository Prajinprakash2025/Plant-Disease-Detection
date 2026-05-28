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

    # 1. Temperature Alerts & Advisories
    if temp > 35:
        alerts.append({
            "level": "danger",
            "icon": "thermometer",
            "title": "Severe Heat Stress Hazard",
            "message": f"Extreme temperature ({temp}°C) detected. Risk of blossom drop, pollen sterilization, and wilting. Water crops deeply during early morning, and consider temporary shading."
        })
    elif temp > 28:
        alerts.append({
            "level": "warning",
            "icon": "thermometer",
            "title": "Warm Temperature Advisory",
            "message": f"Warm conditions ({temp}°C) speed up pest life cycles. Keep a close eye out for aphids, mites, and thrips under leaves."
        })
    elif temp < 5:
        alerts.append({
            "level": "danger",
            "icon": "snowflake",
            "title": "Frost & Freeze Warning",
            "message": f"Freezing temperature ({temp}°C) detected. Extreme danger of cell rupture. Cover tender plants with frost covers and water soil to conserve heat."
        })
    elif temp < 15:
        alerts.append({
            "level": "warning",
            "icon": "snowflake",
            "title": "Cold Growth Retardation",
            "message": f"Chilly temperature ({temp}°C) slows down crop metabolism. Reduce watering and avoid applying nitrogen fertilizers until it warms up."
        })
    else:
        alerts.append({
            "level": "info",
            "icon": "thermometer",
            "title": "Optimal Temperature Range",
            "message": f"Current temperature ({temp}°C) is in the sweet spot for vegetable photosynthesis and crop growth. Ideal for transplanting or sowing."
        })

    # 2. Humidity Alerts & Evapotranspiration
    if humidity > 85:
        alerts.append({
            "level": "danger",
            "icon": "droplets",
            "title": "Severe Humidity Alert",
            "message": f"Extremely high humidity ({humidity}%) reduces plant transpiration and can encourage Downy Mildew and Rust. Avoid adding any water to the foliage directly."
        })
    elif humidity > 70:
        alerts.append({
            "level": "warning",
            "icon": "droplets",
            "title": "Elevated Humidity Advisory",
            "message": f"Humidity is at {humidity}%. Ensure appropriate plant spacing so leaves can dry quickly after dew or rainfall."
        })
    elif humidity < 40:
        alerts.append({
            "level": "danger",
            "icon": "sun",
            "title": "Critical Dry Air Alert",
            "message": f"Dry air ({humidity}%) increases crop transpiration stress and spider mite activity. Ensure soil moisture is adequate; consider mulching."
        })
    elif humidity < 55:
        alerts.append({
            "level": "warning",
            "icon": "sun",
            "title": "Low Humidity Advisory",
            "message": f"Low humidity ({humidity}%) observed. Leaf water loss is accelerated. Check soil dampness."
        })

    # 3. Joint Temp-Humidity Fungal Risk
    if humidity > 80 and 18 <= temp <= 28:
        alerts.append({
            "level": "warning",
            "icon": "droplets",
            "title": "High Fungal Spore Germination",
            "message": f"The combination of warm temperature ({temp}°C) and high humidity ({humidity}%) is the absolute peak window for fungal spore germination (Powdery Mildew, Rust). Enhance airflow."
        })

    # 4. Precipitation Alerts
    if precip > 15: # mm
        alerts.append({
            "level": "danger",
            "icon": "cloud-rain",
            "title": "Heavy Precipitation Warning",
            "message": f"Heavy rain ({precip}mm) observed. High risk of waterlogging, root suffocation, and soil compaction. Ensure all drainage paths are completely clear."
        })
    elif precip > 0.1:
        alerts.append({
            "level": "warning",
            "icon": "cloud-rain",
            "title": "Rain & Splash Spread Risk",
            "message": f"Light rainfall ({precip}mm) detected. Rain splashes transport fungal and bacterial spores from the soil onto lower leaves. Avoid pruning or harvesting right now."
        })
    else:
        # Dry period alert
        if temp > 30:
            alerts.append({
                "level": "warning",
                "icon": "sun",
                "title": "Dry & Warm Spell",
                "message": f"No rainfall combined with warm temperatures ({temp}°C) will dry out soil quickly. Monitor soil moisture levels closely."
            })

    # 5. Wind Alerts
    wind_speed = current.get("wind_speed_10m", 0)
    if wind_speed > 25: # km/h
        alerts.append({
            "level": "danger",
            "icon": "wind",
            "title": "High Wind Hazard",
            "message": f"Very high wind speed ({wind_speed} km/h). Climbing or tall crops may lodge. Check and reinforce stakes, trellises, and support networks."
        })
    elif wind_speed > 12: # km/h
        alerts.append({
            "level": "warning",
            "icon": "wind",
            "title": "Moderate Wind / Spray Alert",
            "message": f"Wind speed is {wind_speed} km/h. Defer any spraying (organic or chemical) to prevent drift and uneven application. Best done when winds die down."
        })
    elif wind_speed < 5 and humidity > 80:
        alerts.append({
            "level": "warning",
            "icon": "wind",
            "title": "Stagnant Air Advisory",
            "message": f"Very calm winds ({wind_speed} km/h) and high humidity ({humidity}%) prevent dew evaporation. Ideal for spore settlement. Consider manual airflow enhancement if in a greenhouse."
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

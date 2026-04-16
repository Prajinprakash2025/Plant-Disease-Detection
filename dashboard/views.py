import math
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import render, redirect
from django.utils import timezone

from account.utils import get_leaf_quota_summary
from detection.models import LeafDiagnosis
from .models import FarmLocation, AgriculturalDataset
from .utils import get_weather_forecast_and_alerts


DASHBOARD_SECTION_CONFIG = {
    "overview": {
        "key": "overview",
        "label": "Overview",
        "template": "dashboard/partials/_overview.html",
    },
    "analytics": {
        "key": "analytics",
        "label": "Analytics",
        "template": "dashboard/partials/_analytics.html",
    },
    "risk": {
        "key": "risk",
        "label": "Risk Board",
        "template": "dashboard/partials/_risk.html",
    },
    "insights": {
        "key": "insights",
        "label": "Insights",
        "template": "dashboard/partials/_insights.html",
    },
    "workflow": {
        "key": "workflow",
        "label": "Workflow",
        "template": "dashboard/partials/_workflow.html",
    },
    "history": {
        "key": "history",
        "label": "Scan History",
        "template": "dashboard/partials/_history.html",
    },
    "weather": {
        "key": "weather",
        "label": "Weather Alerts",
        "template": "dashboard/partials/_weather.html",
    },
    "datasets": {
        "key": "datasets",
        "label": "Historical Datasets",
        "template": "dashboard/partials/_datasets.html",
    },
}


def _round(value, digits=1):
    return round(value, digits) if value is not None else None


def _labeled_logs(queryset):
    return queryset.exclude(predicted_disease__isnull=True).exclude(predicted_disease="")


def _issue_logs(queryset):
    return _labeled_logs(queryset).exclude(predicted_disease__icontains="healthy")


def _healthy_logs(queryset):
    return _labeled_logs(queryset).filter(predicted_disease__icontains="healthy")


def _safe_pct(numerator, denominator):
    if not denominator:
        return 0
    return round((numerator / denominator) * 100, 1)


def _health_score(queryset):
    avg_conf = queryset.exclude(confidence__isnull=True).aggregate(v=Avg("confidence"))["v"]
    if avg_conf is not None:
        return round(avg_conf, 1)

    total = queryset.count()
    if not total:
        return None

    issue_count = _issue_logs(queryset).count()
    return round(((total - issue_count) / total) * 100, 1)


def _recovery_rate(queryset):
    total = queryset.count()
    if not total:
        return 0
    return _safe_pct(_healthy_logs(queryset).count(), total)


def _build_demo_analytics(today):
    trend_30 = []
    heatmap_counts = {}

    for i in range(29, -1, -1):
        current_day = today - timedelta(days=i)
        position = 29 - i
        health = round(69 + (position * 0.58) + math.sin(position / 3.2) * 4.6, 1)
        disease = round(31 - (position * 0.42) + math.cos(position / 4.1) * 3.2, 1)
        scans = max(4, 6 + ((position * 3) % 7))
        trend_30.append(
            {
                "date": current_day.strftime("%b %d"),
                "iso": current_day.isoformat(),
                "health": min(97, max(52, health)),
                "disease": min(48, max(6, disease)),
                "scans": scans,
            }
        )

    for i in range(83, -1, -1):
        current_day = today - timedelta(days=i)
        wave = 3.8 + math.sin(i / 5.5) * 2.6 + math.cos(i / 9.0) * 1.4
        heatmap_counts[current_day.isoformat()] = max(0, int(round(wave + (i % 4))))

    return {
        "using_demo": True,
        "trend_30": trend_30,
        "trend_7": trend_30[-7:],
        "distribution": [
            {"label": "Healthy", "value": 44},
            {"label": "Leaf Spot", "value": 23},
            {"label": "Blight", "value": 18},
            {"label": "Rust", "value": 9},
            {"label": "Mildew", "value": 6},
        ],
        "plant_issues": [
            {"label": "Tomato Field A", "issues": 14},
            {"label": "Pepper Greenhouse", "issues": 11},
            {"label": "Potato Block C", "issues": 9},
            {"label": "Corn Plot 2", "issues": 6},
            {"label": "Apple Orchard East", "issues": 4},
        ],
        "heatmap_counts": heatmap_counts,
    }


def _build_chart_data(diagnosis_logs):
    today = timezone.localdate()

    if not diagnosis_logs.exists():
        return _build_demo_analytics(today)

    trend_30 = []
    for i in range(29, -1, -1):
        current_day = today - timedelta(days=i)
        day_qs = diagnosis_logs.filter(created_at__date=current_day)
        total_scans = day_qs.count()
        issue_count = _issue_logs(day_qs).count()
        trend_30.append(
            {
                "date": current_day.strftime("%b %d"),
                "iso": current_day.isoformat(),
                "health": _health_score(day_qs),
                "disease": _safe_pct(issue_count, total_scans) if total_scans else None,
                "scans": total_scans,
            }
        )

    distribution = list(
        _labeled_logs(diagnosis_logs)
        .values("predicted_disease")
        .annotate(value=Count("id"))
        .order_by("-value")[:6]
    )
    distribution = [
        {"label": item["predicted_disease"], "value": item["value"]}
        for item in distribution
    ]

    plant_issues = list(
        diagnosis_logs.exclude(plant_name__isnull=True)
        .exclude(plant_name="")
        .exclude(predicted_disease__isnull=True)
        .exclude(predicted_disease="")
        .exclude(predicted_disease__icontains="healthy")
        .values("plant_name")
        .annotate(issues=Count("id"))
        .order_by("-issues")[:8]
    )
    plant_issues = [
        {"label": item["plant_name"], "issues": item["issues"]}
        for item in plant_issues
    ]
    if not plant_issues:
        plant_names = list(
            diagnosis_logs.exclude(plant_name__isnull=True)
            .exclude(plant_name="")
            .values_list("plant_name", flat=True)
            .distinct()[:5]
        )
        plant_issues = [{"label": name, "issues": 0} for name in plant_names]

    heatmap_counts = {}
    for i in range(83, -1, -1):
        current_day = today - timedelta(days=i)
        heatmap_counts[current_day.isoformat()] = diagnosis_logs.filter(created_at__date=current_day).count()

    if not distribution:
        demo = _build_demo_analytics(today)
        distribution = demo["distribution"]
    if not plant_issues:
        demo = _build_demo_analytics(today)
        plant_issues = demo["plant_issues"]

    return {
        "using_demo": False,
        "trend_30": trend_30,
        "trend_7": trend_30[-7:],
        "distribution": distribution,
        "plant_issues": plant_issues,
        "heatmap_counts": heatmap_counts,
    }


def _build_weekly_cards(diagnosis_logs, analytics):
    today = timezone.localdate()

    if analytics["using_demo"]:
        return [
            {
                "id": "avg-health",
                "title": "Avg Health Score",
                "value": "84.2%",
                "delta": "+4.6 pts",
                "trend": "up",
                "tone": "emerald",
                "sparkline": [72, 74, 73, 78, 80, 82, 84],
            },
            {
                "id": "week-scans",
                "title": "Total Scans This Week",
                "value": "46",
                "delta": "+8 scans",
                "trend": "up",
                "tone": "emerald",
                "sparkline": [4, 5, 6, 7, 8, 7, 9],
            },
            {
                "id": "issues-detected",
                "title": "Issues Detected",
                "value": "12",
                "delta": "-3 cases",
                "trend": "down",
                "tone": "emerald",
                "sparkline": [5, 4, 4, 3, 3, 2, 2],
            },
            {
                "id": "recovery-rate",
                "title": "Recovery Rate",
                "value": "68.0%",
                "delta": "+7.4 pts",
                "trend": "up",
                "tone": "emerald",
                "sparkline": [52, 54, 57, 60, 62, 65, 68],
            },
        ]

    day_buckets = [
        diagnosis_logs.filter(created_at__date=today - timedelta(days=i))
        for i in range(6, -1, -1)
    ]
    prev_week = diagnosis_logs.filter(
        created_at__date__gte=today - timedelta(days=13),
        created_at__date__lt=today - timedelta(days=6),
    )
    this_week = diagnosis_logs.filter(created_at__date__gte=today - timedelta(days=6))

    avg_health_series = [(_health_score(bucket) or 0) for bucket in day_buckets]
    scan_series = [bucket.count() for bucket in day_buckets]
    issue_series = [_issue_logs(bucket).count() for bucket in day_buckets]
    recovery_series = [_recovery_rate(bucket) for bucket in day_buckets]

    this_avg = _health_score(this_week) or 0
    prev_avg = _health_score(prev_week) or 0
    this_scans = this_week.count()
    prev_scans = prev_week.count()
    this_issues = _issue_logs(this_week).count()
    prev_issues = _issue_logs(prev_week).count()
    this_recovery = _recovery_rate(this_week)
    prev_recovery = _recovery_rate(prev_week)

    return [
        {
            "id": "avg-health",
            "title": "Avg Health Score",
            "value": f"{this_avg:.1f}%",
            "delta": f"{'+' if this_avg >= prev_avg else '-'}{abs(this_avg - prev_avg):.1f} pts",
            "trend": "up" if this_avg >= prev_avg else "down",
            "tone": "emerald" if this_avg >= prev_avg else "amber",
            "sparkline": avg_health_series,
        },
        {
            "id": "week-scans",
            "title": "Total Scans This Week",
            "value": str(this_scans),
            "delta": f"{'+' if this_scans >= prev_scans else '-'}{abs(this_scans - prev_scans)} scans",
            "trend": "up" if this_scans >= prev_scans else "down",
            "tone": "emerald" if this_scans >= prev_scans else "slate",
            "sparkline": scan_series,
        },
        {
            "id": "issues-detected",
            "title": "Issues Detected",
            "value": str(this_issues),
            "delta": f"{'+' if this_issues > prev_issues else '-'}{abs(this_issues - prev_issues)} cases",
            "trend": "up" if this_issues > prev_issues else "down",
            "tone": "red" if this_issues > prev_issues else "emerald",
            "sparkline": issue_series,
        },
        {
            "id": "recovery-rate",
            "title": "Recovery Rate",
            "value": f"{this_recovery:.1f}%",
            "delta": f"{'+' if this_recovery >= prev_recovery else '-'}{abs(this_recovery - prev_recovery):.1f} pts",
            "trend": "up" if this_recovery >= prev_recovery else "down",
            "tone": "emerald" if this_recovery >= prev_recovery else "amber",
            "sparkline": recovery_series,
        },
    ]


def _build_smart_alerts(analytics, weekly_cards, leaf_quota):
    if analytics["using_demo"]:
        return [
            {
                "level": "warning",
                "label": "Warning",
                "icon": "alert-triangle",
                "title": "High risk detected in Tomato crops",
                "body": "Leaf Spot is clustering in Tomato Field A. Prioritize fresh scans and preventive treatment within 48 hours.",
            },
            {
                "level": "info",
                "label": "Action",
                "icon": "scan-line",
                "title": "Apply fungicide within 48 hours",
                "body": "Blight pressure is rising in one greenhouse zone. Review treatment guidance before the next irrigation cycle.",
            },
            {
                "level": "success",
                "label": "Improving",
                "icon": "check-circle-2",
                "title": "Recovery trend is moving in the right direction",
                "body": "Healthy scan share is increasing week over week. Keep monitoring the same fields to confirm the rebound.",
            },
        ]

    alerts = []
    top_issue = analytics["plant_issues"][0] if analytics["plant_issues"] else None
    top_distribution = analytics["distribution"][0] if analytics["distribution"] else None
    issues_card = next((card for card in weekly_cards if card["id"] == "issues-detected"), None)
    recovery_card = next((card for card in weekly_cards if card["id"] == "recovery-rate"), None)

    if top_issue and top_issue["issues"] > 0:
        alerts.append(
            {
                "level": "warning",
                "label": "Warning",
                "icon": "alert-triangle",
                "title": f"High risk detected in {top_issue['label']}",
                "body": f"{top_issue['issues']} flagged scans are concentrated here. Prioritize verification and treatment review for this area first.",
            }
        )

    if top_distribution and "healthy" not in top_distribution["label"].lower():
        alerts.append(
            {
                "level": "info",
                "label": "Action",
                "icon": "scan-line",
                "title": f"{top_distribution['label']} is your top diagnosis pattern",
                "body": "Apply the matching prevention guidance now and use Gemini validation on low-confidence scans before treatment decisions.",
            }
        )

    if recovery_card:
        is_recovering = recovery_card["trend"] == "up"
        alerts.append(
            {
                "level": "success" if is_recovering else "warning",
                "label": "Improving" if is_recovering else "Monitor",
                "icon": "check-circle-2" if is_recovering else "alert-triangle",
                "title": "Recovery rate is trending up" if is_recovering else "Recovery rate slipped this week",
                "body": "Healthy scan share improved compared with the previous week."
                if is_recovering
                else "Healthy scan share dropped this week. Recheck your highest-risk fields before the next scan cycle.",
            }
        )

    remaining = leaf_quota.get("remaining")
    if not leaf_quota.get("is_premium") and remaining is not None and remaining <= 5:
        alerts.append(
            {
                "level": "info",
                "label": "Quota",
                "icon": "clock-3",
                "title": f"Only {remaining} scans remain on free tier",
                "body": "Use the remaining scans on the most affected plants or upgrade before the next monitoring round.",
            }
        )

    return alerts[:3]


def _build_ai_insight(analytics, weekly_cards):
    if analytics["using_demo"]:
        return (
            "Your crop health improved by 12% compared to last week. However, disease detection increased in 2 fields, "
            "with Tomato Field A contributing the highest share of risk. Keep prioritizing verified scans for Leaf Spot and Blight cases."
        )

    avg_card = next((card for card in weekly_cards if card["id"] == "avg-health"), None)
    issue_card = next((card for card in weekly_cards if card["id"] == "issues-detected"), None)
    top_issue = analytics["plant_issues"][0] if analytics["plant_issues"] else None
    top_distribution = analytics["distribution"][0] if analytics["distribution"] else None

    health_phrase = "held steady this week"
    if avg_card:
        if avg_card["trend"] == "up":
            health_phrase = f"improved by {avg_card['delta'].replace('+', '')} compared to last week"
        else:
            health_phrase = f"softened by {avg_card['delta'].replace('-', '')} compared to last week"

    issue_phrase = "issue detection stayed stable across your recent scans"
    if issue_card:
        if issue_card["trend"] == "up":
            issue_phrase = f"issue detection increased by {issue_card['delta'].replace('+', '')}"
        else:
            issue_phrase = f"issue detection dropped by {issue_card['delta'].replace('-', '')}"

    location_phrase = ""
    if top_issue and top_issue["issues"] > 0:
        location_phrase = f", with {top_issue['label']} currently showing the highest problem load"

    disease_phrase = ""
    if top_distribution:
        disease_phrase = f" The most common diagnosis pattern is {top_distribution['label']}."

    return (
        f"Your crop health {health_phrase}, while {issue_phrase}{location_phrase}.{disease_phrase} "
        f"Keep reviewing low-confidence cases quickly so treatment guidance stays ahead of field spread."
    )


def _build_heatmap_weeks(heatmap_counts):
    today = timezone.localdate()
    start_range = today - timedelta(days=83)
    calendar_start = start_range - timedelta(days=start_range.weekday())
    calendar_end = today + timedelta(days=(6 - today.weekday()))
    max_count = max(heatmap_counts.values()) if heatmap_counts else 0

    def level_for(count):
        if count <= 0 or max_count <= 0:
            return 0
        ratio = count / max_count
        if ratio <= 0.25:
            return 1
        if ratio <= 0.5:
            return 2
        if ratio <= 0.75:
            return 3
        return 4

    weeks = []
    current = calendar_start
    while current <= calendar_end:
        week = []
        for _ in range(7):
            count = heatmap_counts.get(current.isoformat(), 0)
            week.append(
                {
                    "date": current.strftime("%b %d, %Y"),
                    "count": count,
                    "level": level_for(count),
                    "muted": current < start_range or current > today,
                }
            )
            current += timedelta(days=1)
        weeks.append(week)
    return weeks


def _resolve_dashboard_section(section_key):
    return DASHBOARD_SECTION_CONFIG.get(section_key, DASHBOARD_SECTION_CONFIG["overview"])


def _build_dashboard_context(user, active_section="overview"):
    section_config = _resolve_dashboard_section(active_section)

    leaf_quota = get_leaf_quota_summary(user)
    diagnosis_logs = LeafDiagnosis.objects.filter(user=user)
    recent_diagnoses = diagnosis_logs[:4]
    verified_count = diagnosis_logs.filter(source=LeafDiagnosis.SOURCE_GEMINI_API).count()
    avg_confidence = diagnosis_logs.exclude(confidence__isnull=True).aggregate(
        avg_confidence=Avg("confidence")
    )["avg_confidence"]
    tracked_plants = (
        diagnosis_logs.exclude(plant_name="")
        .values("plant_name")
        .distinct()
        .count()
    )

    analytics = _build_chart_data(diagnosis_logs)
    weekly_cards = _build_weekly_cards(diagnosis_logs, analytics)
    smart_alerts = _build_smart_alerts(analytics, weekly_cards, leaf_quota)
    ai_insight = _build_ai_insight(analytics, weekly_cards)
    heatmap_weeks = _build_heatmap_weeks(analytics["heatmap_counts"])

    # Load Farm Location and Weather
    farm_location = None
    weather_data = {"current": None, "alerts": [], "daily": []}
    if hasattr(user, 'farm_location'):
        farm_location = user.farm_location
        weather_data = get_weather_forecast_and_alerts(farm_location.latitude, farm_location.longitude)

    # Load Agricultural Datasets
    datasets = AgriculturalDataset.objects.all()

    return {
        "leaf_quota": leaf_quota,
        "recent_diagnoses": recent_diagnoses,
        "dashboard_metrics": {
            "diagnosis_count": diagnosis_logs.count(),
            "verified_count": verified_count,
            "tracked_plants": tracked_plants,
            "avg_confidence": round(avg_confidence, 1)
            if avg_confidence is not None
            else None,
        },
        "analytics": analytics,
        "weekly_cards": weekly_cards,
        "smart_alerts": smart_alerts,
        "ai_insight": ai_insight,
        "heatmap_weeks": heatmap_weeks,
        "farm_location": farm_location,
        "weather_data": weather_data,
        "datasets": datasets,
        "active_section": section_config["key"],
        "active_section_label": section_config["label"],
        "section_template": section_config["template"],
    }


@login_required
def dashboard_home(request):
    context = _build_dashboard_context(
        request.user,
        active_section=request.GET.get("section", "overview"),
    )
    return render(request, "dashboard/home.html", context)


@login_required
def dashboard_section(request, section_key):
    context = _build_dashboard_context(request.user, active_section=section_key)
    return render(request, context["section_template"], context)


@login_required
def update_location(request):
    if request.method == "POST":
        lat = request.POST.get("latitude")
        lon = request.POST.get("longitude")
        city = request.POST.get("city_name", "")
        if lat and lon:
            try:
                lat = float(lat)
                lon = float(lon)
                FarmLocation.objects.update_or_create(
                    user=request.user,
                    defaults={"latitude": lat, "longitude": lon, "city_name": city}
                )
            except ValueError:
                pass
    return redirect("/dashboard/?section=weather")


@login_required
def upload_dataset(request):
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description", "")
        file = request.FILES.get("dataset_file")
        if name and file:
            AgriculturalDataset.objects.create(
                name=name,
                description=description,
                dataset_file=file,
                uploaded_by=request.user
            )
    return redirect("/dashboard/?section=datasets")

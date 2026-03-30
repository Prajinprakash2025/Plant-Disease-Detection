from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import render

from account.utils import get_leaf_quota_summary
from detection.models import LeafDiagnosis


@login_required
def dashboard_home(request):
    leaf_quota = get_leaf_quota_summary(request.user)
    diagnosis_logs = LeafDiagnosis.objects.filter(user=request.user)
    recent_diagnoses = diagnosis_logs[:4]
    verified_count = diagnosis_logs.filter(
        source=LeafDiagnosis.SOURCE_GEMINI_API
    ).count()
    avg_confidence = diagnosis_logs.exclude(confidence__isnull=True).aggregate(
        avg_confidence=Avg("confidence")
    )["avg_confidence"]
    tracked_plants = (
        diagnosis_logs.exclude(plant_name="")
        .values("plant_name")
        .distinct()
        .count()
    )

    return render(
        request,
        "dashboard/home.html",
        {
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
        },
    )

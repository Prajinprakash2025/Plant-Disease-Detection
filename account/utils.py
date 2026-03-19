from django.conf import settings

from .models import MembershipProfile


def get_or_create_membership(user):
    if not getattr(user, "is_authenticated", False):
        return None

    membership, _ = MembershipProfile.objects.get_or_create(user=user)
    return membership


def get_leaf_quota_summary(user):
    membership = get_or_create_membership(user)
    free_limit = int(getattr(settings, "FREE_TIER_LEAF_DIAGNOSIS_LIMIT", 20))
    total_used = user.leaf_diagnosis_logs.count() + user.diagnoses.count()

    if membership and membership.is_premium:
        return {
            "membership": membership,
            "plan_name": membership.get_plan_display(),
            "is_premium": True,
            "used": total_used,
            "limit": None,
            "remaining": None,
            "can_submit": True,
            "limit_reached": False,
            "usage_percent": 100,
            "remaining_percent": 100,
            "usage_label": f"{total_used} scans completed",
            "remaining_label": "Unlimited checks",
        }

    remaining = max(free_limit - total_used, 0)
    usage_percent = int((min(total_used, free_limit) / free_limit) * 100) if free_limit else 0
    remaining_percent = int((remaining / free_limit) * 100) if free_limit else 0

    return {
        "membership": membership,
        "plan_name": membership.get_plan_display() if membership else "Free",
        "is_premium": False,
        "used": total_used,
        "limit": free_limit,
        "remaining": remaining,
        "can_submit": total_used < free_limit,
        "limit_reached": total_used >= free_limit,
        "usage_percent": usage_percent,
        "remaining_percent": remaining_percent,
        "usage_label": f"{total_used} of {free_limit} free scans used",
        "remaining_label": f"{remaining} free scans left",
    }

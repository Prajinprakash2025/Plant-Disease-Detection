import random
import string

from .models import EmailOTP, MembershipProfile


def generate_otp(email, first_name="", last_name="", purpose="login"):
    """Generate a 6-digit OTP and print to terminal."""
    otp = ''.join(random.choices(string.digits, k=6))

    # Invalidate old unused OTPs for this email+purpose
    EmailOTP.objects.filter(email=email, purpose=purpose, is_used=False).update(is_used=True)

    # Create new OTP
    EmailOTP.objects.create(
        email=email,
        otp=otp,
        first_name=first_name,
        last_name=last_name,
        purpose=purpose,
    )

    # Print OTP to terminal (for development)
    print("\n" + "=" * 50)
    print(f"  🔐 OTP for {email}")
    print(f"  Purpose: {purpose.upper()}")
    print(f"  Code:    {otp}")
    print(f"  Expires: 5 minutes")
    print("=" * 50 + "\n")

    return otp


def verify_otp(email, otp_code, purpose="login"):
    """Verify OTP. Returns the OTP object if valid, None otherwise."""
    try:
        otp_obj = EmailOTP.objects.filter(
            email=email,
            otp=otp_code,
            purpose=purpose,
            is_used=False,
        ).latest('created_at')
    except EmailOTP.DoesNotExist:
        return None

    if otp_obj.is_expired:
        return None

    otp_obj.is_used = True
    otp_obj.save(update_fields=['is_used'])
    return otp_obj


def get_or_create_membership(user):
    if not getattr(user, "is_authenticated", False):
        return None

    membership, _ = MembershipProfile.objects.get_or_create(user=user)
    return membership


def get_leaf_quota_summary(user):
    membership = get_or_create_membership(user)
    total_used = user.leaf_diagnosis_logs.count() + user.diagnoses.count()

    return {
        "membership": membership,
        "plan_name": membership.get_plan_display() if membership else "Unlimited",
        "is_premium": bool(membership and membership.is_premium),
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

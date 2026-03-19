from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import AdminLoginForm, ContactForm, LoginForm, SignUpForm, UserProfileForm
from .models import ContactMessage, MembershipProfile
from .utils import get_leaf_quota_summary, get_or_create_membership


def staff_required(view_func):
    actual_decorator = user_passes_test(
        lambda user: user.is_authenticated and user.is_staff,
        login_url="account:admin_login",
    )
    return actual_decorator(view_func)


def _safe_redirect(request, fallback):
    redirect_to = request.POST.get("next") or request.GET.get("next")
    if redirect_to and url_has_allowed_host_and_scheme(
        url=redirect_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect_to
    return fallback


def home(request):
    return render(request, "account/home.html")


def about_view(request):
    return render(request, "account/about.html")


def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            ContactMessage.objects.create(**form.cleaned_data)
            messages.success(
                request,
                "Your message has been received. We will get back to you soon.",
            )
            return redirect("account:contact")
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {
                "name": request.user.get_full_name() or request.user.username,
                "email": request.user.email,
            }
        form = ContactForm(initial=initial)

    return render(request, "account/contact.html", {"form": form})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    next_url = request.POST.get("next") or request.GET.get("next", "")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            get_or_create_membership(user)
            login(request, user)
            messages.success(request, "Your account has been created.")
            return redirect(_safe_redirect(request, "dashboard:home"))
    else:
        form = SignUpForm()

    return render(request, "account/signup.html", {"form": form, "next_url": next_url})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    next_url = request.POST.get("next") or request.GET.get("next", "")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Welcome back.")
            return redirect(_safe_redirect(request, settings.LOGIN_REDIRECT_URL))
    else:
        form = LoginForm(request)

    return render(request, "account/login.html", {"form": form, "next_url": next_url})


def admin_login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("account:admin_dashboard")

    next_url = request.POST.get("next") or request.GET.get("next", "")

    if request.method == "POST":
        form = AdminLoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Admin access granted.")
            return redirect(_safe_redirect(request, "account:admin_dashboard"))
    else:
        form = AdminLoginForm(request)

    return render(
        request,
        "account/admin/login.html",
        {"form": form, "next_url": next_url},
    )


@require_POST
def admin_logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, "Admin session closed.")
    return redirect("account:admin_login")


def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, "You have been logged out.")
    return redirect("account:home")


@login_required
def profile_view(request):
    membership = get_or_create_membership(request.user)
    leaf_quota = get_leaf_quota_summary(request.user)

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("account:profile")
    else:
        form = UserProfileForm(instance=request.user)

    return render(
        request,
        "account/profile.html",
        {
            "form": form,
            "joined_date": request.user.date_joined,
            "last_login": request.user.last_login,
            "profile_completion": _profile_completion(request.user),
            "membership": membership,
            "leaf_quota": leaf_quota,
        },
    )


@login_required
def membership_view(request):
    membership = get_or_create_membership(request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "activate_premium":
            membership.plan = MembershipProfile.PLAN_PREMIUM
            membership.upgraded_at = timezone.now()
            membership.save(update_fields=["plan", "upgraded_at", "updated_at"])
            messages.success(
                request,
                "Premium demo mode is active. Your leaf checks are now unlimited.",
            )
            return redirect("account:membership")

        if action == "switch_free":
            membership.plan = MembershipProfile.PLAN_FREE
            membership.save(update_fields=["plan", "updated_at"])
            messages.success(
                request,
                "Your account has been switched back to the free plan.",
            )
            return redirect("account:membership")

    return render(
        request,
        "account/membership.html",
        {
            "membership": membership,
            "leaf_quota": get_leaf_quota_summary(request.user),
        },
    )


@staff_required
def admin_dashboard_view(request):
    week_ago = timezone.now() - timedelta(days=7)
    users = User.objects.order_by("-date_joined")
    contact_messages = ContactMessage.objects.order_by("-created_at")

    context = {
        "total_users": users.count(),
        "active_users": users.filter(is_active=True).count(),
        "blocked_users": users.filter(is_active=False).count(),
        "staff_users": users.filter(is_staff=True).count(),
        "new_users_this_week": users.filter(date_joined__gte=week_ago).count(),
        "unresolved_messages": contact_messages.filter(is_resolved=False).count(),
        "recent_users": users[:6],
        "recent_messages": contact_messages[:6],
    }
    return render(request, "account/admin/dashboard.html", context)


@staff_required
def admin_users_view(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")

    users = User.objects.order_by("-date_joined")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )

    if status == "active":
        users = users.filter(is_active=True)
    elif status == "blocked":
        users = users.filter(is_active=False)
    elif status == "staff":
        users = users.filter(is_staff=True)

    paginator = Paginator(users, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "account/admin/users.html",
        {
            "page_obj": page_obj,
            "query": query,
            "status": status,
            "total_results": users.count(),
        },
    )


@staff_required
def admin_messages_view(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")

    contact_messages = ContactMessage.objects.order_by("-created_at")
    if query:
        contact_messages = contact_messages.filter(
            Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(subject__icontains=query)
            | Q(message__icontains=query)
        )

    if status == "open":
        contact_messages = contact_messages.filter(is_resolved=False)
    elif status == "resolved":
        contact_messages = contact_messages.filter(is_resolved=True)

    paginator = Paginator(contact_messages, 8)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "account/admin/messages.html",
        {
            "page_obj": page_obj,
            "query": query,
            "status": status,
            "total_results": contact_messages.count(),
        },
    )


@staff_required
@require_POST
def toggle_user_active_view(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot block your own admin account.")
        return redirect(_safe_redirect(request, "account:admin_users"))

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])

    action = "reactivated" if target_user.is_active else "blocked"
    messages.success(request, f"{target_user.username} has been {action}.")
    return redirect(_safe_redirect(request, "account:admin_users"))


@staff_required
@require_POST
def toggle_user_staff_view(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot remove your own admin access.")
        return redirect(_safe_redirect(request, "account:admin_users"))

    target_user.is_staff = not target_user.is_staff
    target_user.save(update_fields=["is_staff"])

    action = "granted admin access" if target_user.is_staff else "removed from admin access"
    messages.success(request, f"{target_user.username} was {action}.")
    return redirect(_safe_redirect(request, "account:admin_users"))


@staff_required
@require_POST
def toggle_message_resolved_view(request, message_id):
    message_obj = get_object_or_404(ContactMessage, pk=message_id)
    message_obj.is_resolved = not message_obj.is_resolved
    message_obj.save(update_fields=["is_resolved"])

    state = "resolved" if message_obj.is_resolved else "reopened"
    messages.success(request, f"Message '{message_obj.subject}' marked as {state}.")
    return redirect(_safe_redirect(request, "account:admin_messages"))


def _profile_completion(user):
    checks = [user.first_name, user.last_name, user.email, user.username]
    completed = sum(bool(value) for value in checks)
    return int((completed / len(checks)) * 100)

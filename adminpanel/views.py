from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from account.models import ContactMessage

from .forms import AdminLoginForm


def staff_required(view_func):
    actual_decorator = user_passes_test(
        lambda user: user.is_authenticated and user.is_staff,
        login_url="adminpanel:login",
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


def admin_login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("adminpanel:dashboard")

    next_url = request.POST.get("next") or request.GET.get("next", "")

    if request.method == "POST":
        form = AdminLoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Admin access granted.")
            return redirect(_safe_redirect(request, "adminpanel:dashboard"))
    else:
        form = AdminLoginForm(request)

    return render(
        request,
        "adminpanel/login.html",
        {"form": form, "next_url": next_url},
    )


@require_POST
def admin_logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, "Admin session closed.")
    return redirect("adminpanel:login")


@staff_required
def dashboard_view(request):
    week_ago = timezone.now() - timedelta(days=7)
    users = User.objects.order_by("-date_joined")
    messages_qs = ContactMessage.objects.order_by("-created_at")

    context = {
        "total_users": users.count(),
        "active_users": users.filter(is_active=True).count(),
        "blocked_users": users.filter(is_active=False).count(),
        "staff_users": users.filter(is_staff=True).count(),
        "new_users_this_week": users.filter(date_joined__gte=week_ago).count(),
        "unresolved_messages": messages_qs.filter(is_resolved=False).count(),
        "recent_users": users[:6],
        "recent_messages": messages_qs[:6],
    }
    return render(request, "adminpanel/dashboard.html", context)


@staff_required
def users_view(request):
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
        "adminpanel/users.html",
        {
            "page_obj": page_obj,
            "query": query,
            "status": status,
            "total_results": users.count(),
        },
    )


@staff_required
def messages_view(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")

    messages_qs = ContactMessage.objects.order_by("-created_at")
    if query:
        messages_qs = messages_qs.filter(
            Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(subject__icontains=query)
            | Q(message__icontains=query)
        )

    if status == "open":
        messages_qs = messages_qs.filter(is_resolved=False)
    elif status == "resolved":
        messages_qs = messages_qs.filter(is_resolved=True)

    paginator = Paginator(messages_qs, 8)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "adminpanel/messages.html",
        {
            "page_obj": page_obj,
            "query": query,
            "status": status,
            "total_results": messages_qs.count(),
        },
    )


@staff_required
@require_POST
def toggle_user_active_view(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot block your own admin account.")
        return redirect(_safe_redirect(request, "adminpanel:users"))

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])

    action = "reactivated" if target_user.is_active else "blocked"
    messages.success(request, f"{target_user.username} has been {action}.")
    return redirect(_safe_redirect(request, "adminpanel:users"))


@staff_required
@require_POST
def toggle_user_staff_view(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot remove your own admin access.")
        return redirect(_safe_redirect(request, "adminpanel:users"))

    target_user.is_staff = not target_user.is_staff
    target_user.save(update_fields=["is_staff"])

    action = "granted admin access" if target_user.is_staff else "removed from admin access"
    messages.success(request, f"{target_user.username} was {action}.")
    return redirect(_safe_redirect(request, "adminpanel:users"))


@staff_required
@require_POST
def toggle_message_resolved_view(request, message_id):
    message_obj = get_object_or_404(ContactMessage, pk=message_id)
    message_obj.is_resolved = not message_obj.is_resolved
    message_obj.save(update_fields=["is_resolved"])

    state = "resolved" if message_obj.is_resolved else "reopened"
    messages.success(request, f"Message '{message_obj.subject}' marked as {state}.")
    return redirect(_safe_redirect(request, "adminpanel:messages"))

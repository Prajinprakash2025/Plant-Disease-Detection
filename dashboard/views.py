from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from account.utils import get_leaf_quota_summary


@login_required
def dashboard_home(request):
    return render(
        request,
        "dashboard/home.html",
        {"leaf_quota": get_leaf_quota_summary(request.user)},
    )

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class DashboardViewTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(
            response,
            f"{reverse('account:login')}?next={reverse('dashboard:home')}",
        )

    def test_dashboard_section_requires_login(self):
        response = self.client.get(reverse("dashboard:section", args=["overview"]))
        self.assertRedirects(
            response,
            f"{reverse('account:login')}?next={reverse('dashboard:section', args=['overview'])}",
        )

    def test_dashboard_renders_for_authenticated_user(self):
        user = User.objects.create_user(username="grower", password="StrongPass123!")
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)

    def test_dashboard_section_renders_for_authenticated_user(self):
        user = User.objects.create_user(username="grower2", password="StrongPass123!")
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard:section", args=["history"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Latest diagnosis activity")

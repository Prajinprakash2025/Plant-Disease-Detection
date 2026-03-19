from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import ContactMessage, MembershipProfile


class AccountViewTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse("account:home"))
        self.assertEqual(response.status_code, 200)

    def test_about_page_renders(self):
        response = self.client.get(reverse("account:about"))
        self.assertEqual(response.status_code, 200)

    def test_contact_page_accepts_submission(self):
        response = self.client.post(
            reverse("account:contact"),
            {
                "name": "Aarav Sharma",
                "email": "aarav@example.com",
                "subject": "Demo",
                "message": "I need help setting up image diagnosis.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your message has been received.")
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_signup_creates_user_and_logs_them_in(self):
        response = self.client.post(
            reverse("account:signup"),
            {
                "first_name": "Aarav",
                "last_name": "Sharma",
                "username": "aarav",
                "email": "aarav@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("dashboard:home"))
        self.assertTrue(User.objects.filter(username="aarav").exists())

    def test_login_page_authenticates_user(self):
        User.objects.create_user(
            username="farmer",
            email="farmer@example.com",
            password="StrongPass123!",
        )

        response = self.client.post(
            reverse("account:login"),
            {"username": "farmer", "password": "StrongPass123!"},
        )

        self.assertRedirects(response, reverse("dashboard:home"))

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse("account:profile"))
        self.assertRedirects(
            response,
            f"{reverse('account:login')}?next={reverse('account:profile')}",
        )

    def test_membership_page_requires_authentication(self):
        response = self.client.get(reverse("account:membership"))
        self.assertRedirects(
            response,
            f"{reverse('account:login')}?next={reverse('account:membership')}",
        )

    def test_user_can_activate_premium_demo_membership(self):
        user = User.objects.create_user(
            username="member",
            email="member@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("account:membership"),
            {"action": "activate_premium"},
            follow=True,
        )

        membership = MembershipProfile.objects.get(user=user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(membership.plan, MembershipProfile.PLAN_PREMIUM)
        self.assertContains(response, "Premium demo mode is active")


class AccountAdminViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="adminuser",
            email="admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="farmer",
            email="farmer@example.com",
            password="StrongPass123!",
        )
        self.contact_message = ContactMessage.objects.create(
            name="Aarav Sharma",
            email="aarav@example.com",
            subject="Need support",
            message="Please review the latest crop issue.",
        )

    def test_admin_dashboard_requires_staff_login(self):
        response = self.client.get(reverse("account:admin_dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('account:admin_login')}?next={reverse('account:admin_dashboard')}",
        )

    def test_admin_login_allows_staff_user(self):
        response = self.client.post(
            reverse("account:admin_login"),
            {"username": "adminuser", "password": "StrongPass123!"},
        )

        self.assertRedirects(response, reverse("account:admin_dashboard"))

    def test_admin_login_rejects_regular_user(self):
        response = self.client.post(
            reverse("account:admin_login"),
            {"username": "farmer", "password": "StrongPass123!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not have admin access")

    def test_staff_can_block_and_unblock_user(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("account:toggle_user_active", args=[self.regular_user.id]),
        )
        self.assertRedirects(response, reverse("account:admin_users"))
        self.regular_user.refresh_from_db()
        self.assertFalse(self.regular_user.is_active)

        self.client.post(
            reverse("account:toggle_user_active", args=[self.regular_user.id]),
        )
        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.is_active)

    def test_staff_can_toggle_message_resolved(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("account:toggle_message_resolved", args=[self.contact_message.id]),
        )

        self.assertRedirects(response, reverse("account:admin_messages"))
        self.contact_message.refresh_from_db()
        self.assertTrue(self.contact_message.is_resolved)

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User


class StyledFieldsMixin:
    placeholders = {}
    autocomplete_map = {}

    def style_fields(self):
        for field_name, field in self.fields.items():
            classes = field.widget.attrs.get("class", "").split()
            classes.append("form-input")
            if isinstance(field.widget, forms.Textarea):
                classes.append("form-textarea")
            field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))
            if field_name in self.placeholders:
                field.widget.attrs["placeholder"] = self.placeholders[field_name]
            if field_name in self.autocomplete_map:
                field.widget.attrs["autocomplete"] = self.autocomplete_map[field_name]


class SignUpForm(StyledFieldsMixin, forms.Form):
    """Step 1: Collect name + email for signup."""
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()

    placeholders = {
        "first_name": "First name",
        "last_name": "Last name",
        "email": "you@example.com",
    }
    autocomplete_map = {
        "first_name": "given-name",
        "last_name": "family-name",
        "email": "email",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Please login instead.")
        return email


class OTPVerifyForm(StyledFieldsMixin, forms.Form):
    """Step 2: Enter OTP code."""
    otp = forms.CharField(max_length=6, min_length=6, label="OTP Code")

    placeholders = {"otp": "Enter 6-digit code"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
        self.fields["otp"].widget.attrs.update({
            "inputmode": "numeric",
            "pattern": "[0-9]*",
            "autofocus": "autofocus",
            "style": "text-align:center; font-size:1.5rem; letter-spacing:0.5em; font-weight:800",
        })


class LoginEmailForm(StyledFieldsMixin, forms.Form):
    """Step 1: Enter email for login."""
    email = forms.EmailField()

    placeholders = {"email": "you@example.com"}
    autocomplete_map = {"email": "email"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("No account found with this email. Please sign up first.")
        return email


class LoginForm(StyledFieldsMixin, forms.Form):
    """Kept for admin login compatibility. Regular login uses LoginEmailForm."""
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

    placeholders = {
        "username": "Enter your username",
        "password": "Enter your password",
    }
    autocomplete_map = {
        "username": "username",
        "password": "current-password",
    }

    def __init__(self, *args, **kwargs):
        # Accept request arg for compatibility but ignore it
        kwargs.pop('request', None)
        if args:
            args = args[1:]  # skip request positional arg
        super().__init__(*args, **kwargs)
        self.style_fields()


class AdminLoginForm(StyledFieldsMixin, AuthenticationForm):
    placeholders = {
        "username": "Admin username",
        "password": "Admin password",
    }
    autocomplete_map = {
        "username": "username",
        "password": "current-password",
    }

    error_messages = {
        **AuthenticationForm.error_messages,
        "not_staff": "This account does not have admin access.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        if self.user_cache and not self.user_cache.is_staff:
            raise forms.ValidationError(
                self.error_messages["not_staff"],
                code="not_staff",
            )
        return cleaned_data


class UserProfileForm(StyledFieldsMixin, forms.ModelForm):
    placeholders = {
        "first_name": "First name",
        "last_name": "Last name",
        "username": "Username",
        "email": "Email address",
    }
    autocomplete_map = {
        "first_name": "given-name",
        "last_name": "family-name",
        "username": "username",
        "email": "email",
    }

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        query = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if query.exists():
            raise forms.ValidationError("This email is already linked to another account.")
        return email


class ContactForm(StyledFieldsMixin, forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))

    placeholders = {
        "name": "Your full name",
        "email": "you@example.com",
        "subject": "How can we help?",
        "message": "Tell us about your plant disease detection requirement or question.",
    }
    autocomplete_map = {
        "name": "name",
        "email": "email",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

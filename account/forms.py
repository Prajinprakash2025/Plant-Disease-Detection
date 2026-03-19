from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
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


class SignUpForm(StyledFieldsMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()

    placeholders = {
        "first_name": "Aarav",
        "last_name": "Sharma",
        "username": "farmer_aarav",
        "email": "name@example.com",
        "password1": "Create a password",
        "password2": "Confirm your password",
    }
    autocomplete_map = {
        "first_name": "given-name",
        "last_name": "family-name",
        "username": "username",
        "email": "email",
        "password1": "new-password",
        "password2": "new-password",
    }

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
        self.fields["username"].help_text = "Use letters, numbers, and @/./+/-/_ only."
        self.fields["password1"].help_text = (
            "Use at least 8 characters and avoid common passwords."
        )
        self.fields["password2"].help_text = "Enter the same password again for verification."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip().lower()
        if commit:
            user.save()
        return user


class LoginForm(StyledFieldsMixin, AuthenticationForm):
    placeholders = {
        "username": "Enter your username",
        "password": "Enter your password",
    }
    autocomplete_map = {
        "username": "username",
        "password": "current-password",
    }

    def __init__(self, *args, **kwargs):
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

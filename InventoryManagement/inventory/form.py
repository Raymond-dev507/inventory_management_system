from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm

from .models import SystemSettings
from .user_helpers import (
    can_assign_group,
    can_edit_user,
)


# =========================================================
# CREATE USER FORM
# =========================================================

class CreateUserForm(UserCreationForm):

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Enter email address"
        })
    )

    groups = forms.ModelChoiceField(
        queryset=Group.objects.none(),
        required=False,
        empty_label="Select a role",
        widget=forms.Select(attrs={
            "class": "form-select"
        })
    )

    is_active = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input"
        })
    )

    class Meta:

        model = User

        fields = [
            "username",
            "email",
            "password1",
            "password2",
            "groups",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):

        self.request = kwargs.pop(
            "request",
            None
        )

        super().__init__(*args, **kwargs)

        # -------------------------------------------------
        # ROLE DROPDOWN
        #
        # Everyone sees every group. Security is enforced
        # at submit time in clean_groups(), not by hiding
        # options — this keeps the two forms consistent and
        # avoids a second place where the rule could drift.
        # -------------------------------------------------

        if self.request:
            self.fields["groups"].queryset = Group.objects.all()

        # -------------------------------------------------
        # STYLING
        # -------------------------------------------------

        self.fields["username"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Enter username"
        })

        self.fields["password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Enter password"
        })

        self.fields["password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Confirm password"
        })

    # -----------------------------------------------------
    # ROLE SECURITY
    # -----------------------------------------------------

    def clean_groups(self):

        group = self.cleaned_data.get("groups")

        if not group:
            return group

        current_user = self.request.user

        if current_user.is_superuser:
            return group

        if not can_assign_group(current_user, group):

            raise forms.ValidationError(
                f"You cannot assign the '{group.name}' role. "
                "You can only assign a role below your own authority."
            )

        return group

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    def save(self, commit=True):

        user = super().save(commit=False)

        user.email = self.cleaned_data.get("email", "")
        user.is_active = self.cleaned_data.get("is_active", True)

        # Never create Django privileged accounts
        # from this form.
        user.is_superuser = False
        user.is_staff = False

        if commit:

            user.save()

            group = self.cleaned_data.get("groups")

            if group:
                user.groups.set([group])
            else:
                user.groups.clear()

        return user


# =========================================================
# EDIT USER FORM
# =========================================================

class EditUserForm(forms.ModelForm):

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Enter email address"
        })
    )

    groups = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        empty_label="Select a role",
        widget=forms.Select(attrs={
            "class": "form-select"
        })
    )

    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input"
        })
    )

    class Meta:

        model = User

        fields = [
            "username",
            "email",
            "groups",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):

        self.request = kwargs.pop("request", None)

        super().__init__(*args, **kwargs)

        current_user = self.request.user

        # -------------------------------------------------
        # WHO CAN EVEN OPEN THIS EDIT AT ALL?
        #
        # can_assign_group() only ever protected the GROUP
        # field. It never stopped a lower-authority user
        # from changing a higher/equal user's username,
        # email, or active status. This is the fix: if the
        # requester isn't allowed to edit this person at
        # all (per can_edit_user), lock every field so the
        # form can be viewed but not used to change anything.
        # -------------------------------------------------

        self.can_edit_target = (
            current_user.is_superuser
            or can_edit_user(current_user, self.instance)
        )

        if not self.can_edit_target:

            for field in self.fields.values():
                field.disabled = True

            self.fields["groups"].help_text = (
                "You do not have permission to edit this user."
            )

        # -------------------------------------------------
        # SHOW ALL GROUPS
        #
        # Manager can SEE Manager here. Security is not
        # based on hiding the option — it's checked on
        # submit, in clean_groups() and again in save().
        # -------------------------------------------------

        self.fields["groups"].queryset = Group.objects.all()

        current_group = self.instance.groups.first()

        if current_group:
            self.fields["groups"].initial = current_group

        # -------------------------------------------------
        # STYLING
        # -------------------------------------------------

        self.fields["username"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Enter username"
        })

    # =====================================================
    # WHOLE-FORM VALIDATION
    #
    # Defense in depth: even if a disabled field were
    # tampered with client-side, block the entire submit
    # here before anything is saved.
    # =====================================================

    def clean(self):

        cleaned_data = super().clean()

        if not self.can_edit_target:

            raise forms.ValidationError(
                "You do not have permission to edit this user."
            )

        return cleaned_data

    # =====================================================
    # ROLE VALIDATION
    # =====================================================

    def clean_groups(self):

        group = self.cleaned_data.get("groups")

        current_user = self.request.user

        if current_user.is_superuser:
            return group

        if not group:
            return group

        if not can_assign_group(current_user, group):

            raise forms.ValidationError(
                f"You cannot assign the '{group.name}' role. "
                "You can only assign a role below your own authority."
            )

        return group

    # =====================================================
    # SAVE
    #
    # All permission checks now happen in clean()/
    # clean_groups() BEFORE save() runs at all — Django
    # only calls save() after is_valid() passes. Nothing
    # here writes to the database until every check has
    # already succeeded, so there's no partial-write risk.
    # =====================================================

    def save(self, commit=True):

        user = super().save(commit=False)

        # Never change Django privilege flags through
        # this form, regardless of who's submitting it.
        user.is_superuser = self.instance.is_superuser
        user.is_staff = self.instance.is_staff

        if commit:

            user.save()

            group = self.cleaned_data.get("groups")

            if group:
                user.groups.set([group])
            else:
                user.groups.clear()

        return user


CURRENCY_CHOICES = [
    ("₦", "Nigerian Naira (₦)"),
    ("$", "US Dollar ($)"),
    ("€", "Euro (€)"),
    ("£", "British Pound (£)"),
    ("R", "South African Rand (R)"),
    ("KSh", "Kenyan Shilling (KSh)"),
    ("GH₵", "Ghanaian Cedi (GH₵)"),
]


class SystemSettingsForm(forms.ModelForm):
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )

    class Meta:
        model = SystemSettings
        fields = [
            # Business Information
            "business_name",
            "phone",
            "email",
            "address",
            "website",
            "tax_number",

            # General Preferences
            "currency",
            "date_format",
            "time_format",
            "default_payment_method",

            # Inventory Settings
            "low_stock_threshold",
            "allow_negative_stock",
            "auto_deduct_stock",

            # Receipt Settings
            "receipt_footer",
            "receipt_show_cashier",
            "receipt_show_customer",
            "receipt_show_payment_method",
            "receipt_show_sku",

            # Notification Settings
            "low_stock_notifications",
            "out_of_stock_notifications",
            "daily_report_enabled",
            "daily_report_time",

            # AI Report Settings
            "ai_report_enabled",
            "ai_report_time",
        ]

        widgets = {

            # ---- Business Information ----
            "business_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter business name",
            }),
            "phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter phone number",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "Enter email address",
            }),
            "address": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Enter business address",
            }),
            "website": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://example.com",
            }),
            "tax_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Business registration / tax number",
            }),

            # ---- General Preferences ----
            # currency widget removed — now a declared ChoiceField above

            "date_format": forms.Select(attrs={
                "class": "form-select",
            }),
            "time_format": forms.Select(attrs={
                "class": "form-select",
            }),
            "default_payment_method": forms.Select(attrs={
                "class": "form-select",
            }),

            # ---- Inventory Settings ----
            "low_stock_threshold": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0,
            }),
            "allow_negative_stock": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "auto_deduct_stock": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),

            # ---- Receipt Settings ----
            "receipt_footer": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Thank you for your patronage.",
            }),
            "receipt_show_cashier": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "receipt_show_customer": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "receipt_show_payment_method": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "receipt_show_sku": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),

            # ---- Notification Settings ----
            "low_stock_notifications": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "out_of_stock_notifications": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "daily_report_enabled": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "daily_report_time": forms.TimeInput(attrs={
                "class": "form-control",
                "type": "time",
            }),

            # ---- AI Report Settings ----
            "ai_report_enabled": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "ai_report_time": forms.TimeInput(attrs={
                "class": "form-control",
                "type": "time",
            }),
        }

    def clean_low_stock_threshold(self):
        value = self.cleaned_data["low_stock_threshold"]
        if value < 0:
            raise forms.ValidationError("Low stock threshold cannot be negative.")
        return value
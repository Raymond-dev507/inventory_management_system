from datetime import time

from django.db import models
from django.contrib.auth.models import User
# Create your models here.

class Category(models.Model):
    name = models.CharField(max_length=40)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Supplier(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True,null=True)
    address = models.TextField(blank=True,null=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="products")

    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)

    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)

    description = models.TextField(blank=True)
    quantity = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def profit(self):
        return self.selling_price - self.cost_price

    @property
    def is_oversold(self):
        """True if stock has been sold past 0 (only possible
        when allow_negative_stock was enabled at sale time)."""
        return self.quantity < 0

    @property
    def display_quantity(self):
        """Quantity for UI display — never a raw negative
        number, floors at 0 instead."""
        return max(self.quantity, 0)

    @property
    def oversold_by(self):
        """How many units past 0 this product is oversold by.
        e.g. quantity=-3 returns 3. Returns 0 if not oversold."""
        return abs(self.quantity) if self.quantity < 0 else 0

    def __str__(self):
        return self.name



class StockIn(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    quantity = models.PositiveIntegerField()

    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"

class StockOut(models.Model):

    REASON_CHOICES = [
        ("sale", "Sale"),
        ("damaged", "Damaged"),
        ("expired", "Expired"),
        ("returned", "Returned"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    quantity = models.PositiveIntegerField()
    note = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default="sale")
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"



class Sale(models.Model):

    PAYMENT_METHODS = [
        ("cash", "Cash"),
        ("transfer", "Bank Transfer"),
        ("pos", "POS"),
    ]

    customer_name = models.CharField(
        max_length=100,
        blank=True
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default="cash"
    )

    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    date = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Sale #{self.id}"



class SaleItem(models.Model):

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name = "sale_items"
    )

    quantity = models.PositiveIntegerField()

    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )
    stock_deducted = models.BooleanField(default=True)
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class ActivityLog(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="activity_logs"
    )

    action = models.CharField(
        max_length=50
    )

    description = models.TextField()

    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.user.username} - {self.action}"





class SystemSettings(models.Model):

    # ==========================================================
    # BUSINESS INFORMATION
    # ==========================================================

    business_name = models.CharField(
        max_length=200,
        default="My Inventory Store"
    )

    phone = models.CharField(
        max_length=30,
        blank=True
    )

    email = models.EmailField(
        blank=True
    )

    address = models.TextField(
        blank=True
    )

    website = models.URLField(
        blank=True
    )

    tax_number = models.CharField(
        max_length=100,
        blank=True
    )

    # ==========================================================
    # GENERAL PREFERENCES
    # ==========================================================

    currency = models.CharField(
        max_length=10,
        default="₦"
    )

    date_format = models.CharField(
        max_length=20,
        choices=[
            ("d/m/Y", "DD/MM/YYYY"),
            ("m/d/Y", "MM/DD/YYYY"),
            ("Y-m-d", "YYYY-MM-DD"),
        ],
        default="d/m/Y"
    )

    time_format = models.CharField(
        max_length=10,
        choices=[
            ("12", "12-hour"),
            ("24", "24-hour"),
        ],
        default="12"
    )

    default_payment_method = models.CharField(
        max_length=20,
        choices=[
            ("cash", "Cash"),
            ("transfer", "Bank Transfer"),
            ("pos", "POS"),
        ],
        default="cash"
    )

    # ==========================================================
    # INVENTORY SETTINGS
    # ==========================================================

    low_stock_threshold = models.PositiveIntegerField(
        default=5
    )

    allow_negative_stock = models.BooleanField(
        default=False
    )

    auto_deduct_stock = models.BooleanField(
        default=True
    )

    # ==========================================================
    # RECEIPT SETTINGS
    # ==========================================================

    receipt_footer = models.TextField(
        blank=True,
        default="Thank you for your patronage."
    )

    receipt_show_cashier = models.BooleanField(
        default=True
    )

    receipt_show_customer = models.BooleanField(
        default=True
    )

    receipt_show_payment_method = models.BooleanField(
        default=True
    )

    receipt_show_sku = models.BooleanField(
        default=True
    )

    # ==========================================================
    # NOTIFICATION SETTINGS
    # ==========================================================

    low_stock_notifications = models.BooleanField(
        default=True
    )

    out_of_stock_notifications = models.BooleanField(
        default=True
    )

    daily_report_enabled = models.BooleanField(
        default=False
    )

    daily_report_time = models.TimeField(
        default=time(20, 0)
    )

    # ==========================================================
    # AI REPORT SETTINGS
    # ==========================================================

    ai_report_enabled = models.BooleanField(
        default=False
    )

    ai_report_time = models.TimeField(
        default=time(20, 0)
    )

    # ---- Send tracking (prevents duplicate sends per day) ----

    last_daily_report_sent = models.DateField(
        null=True,
        blank=True
    )

    last_ai_report_sent = models.DateField(
        null=True,
        blank=True
    )

    # ==========================================================
    # SYSTEM
    # ==========================================================

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.business_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Prevent deletion of the singleton settings row.
        pass

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj








class AuthorizedTelegramUser(models.Model):
    """
    Controls who is allowed to talk to the store's
    Telegram bot.

    Only chat_ids in this table (with is_active=True) are
    even considered — and in practice, only a superuser's
    linked_user will actually be granted access by the
    webhook. Non-superusers are blocked entirely, even if
    a row exists here.
    """

    telegram_chat_id = models.BigIntegerField(
        unique=True,
    )

    telegram_username = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    linked_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        help_text=(
            "The store's internal user account this "
            "Telegram chat belongs to. Only superusers "
            "are actually granted bot access."
        ),
    )

    is_active = models.BooleanField(
        default=True,
    )

    added_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        access = (
            "Superuser (full access)"
            if self.linked_user.is_superuser
            else "No access (not superuser)"
        )

        return (
            f"{self.telegram_username or self.telegram_chat_id} "
            f"({self.linked_user.username} — {access})"
        )


class UserDeletionRecord(models.Model):
    """
    Marks a user as soft-deleted.

    Soft-deleted is different from merely deactivated:

    - Deactivated (is_active=False, no record here) still
      shows in the Users list with an "Inactive" badge, and
      can be reactivated.

    - Soft-deleted (is_active=False AND a record here) is
      hidden from the Users list entirely, as if removed —
      but every Sale, ActivityLog, etc. tied to this user
      stays fully intact, since we never actually delete the
      User row.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="deletion_record",
    )

    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )

    deleted_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return f"{self.user.username} — deleted {self.deleted_at:%d %b %Y}"








class ConversationContext(models.Model):


    telegram_chat_id = models.BigIntegerField(
        unique=True,
    )

    last_product_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    last_supplier_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return f"Context for {self.telegram_chat_id}"
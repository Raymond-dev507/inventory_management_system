# Updated `get_daily_store_data()` — Supplier and Product Data
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, HttpResponse

from .models import Product, Sale, SaleItem, ActivityLog, SystemSettings
from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Value, Q

from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models.functions import TruncDate, Coalesce


def get_daily_store_data():

    # ==========================================
    # TIME RANGE
    # ==========================================

    products = Product.objects.select_related(
        "supplier",
        "category"
    ).all()

    now = timezone.now()

    start_of_day = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    end_of_day = start_of_day + timedelta(days=1)


    # ==========================================
    # TODAY'S SALE ITEMS
    # ==========================================

    today_sale_items = SaleItem.objects.filter(
        sale__date__gte=start_of_day,
        sale__date__lt=end_of_day
    )


    # ==========================================
    # TOTAL REVENUE
    # ==========================================

    total_revenue = (
        today_sale_items.aggregate(
            total=Sum("subtotal")
        )["total"] or 0
    )


    # ==========================================
    # TOTAL UNITS SOLD
    # ==========================================

    total_units_sold = (
        today_sale_items.aggregate(
            total=Sum("quantity")
        )["total"] or 0
    )


    # ==========================================
    # TOTAL PROFIT
    # ==========================================

    total_profit = (
        today_sale_items.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") *
                    (
                        F("unit_price") -
                        F("product__cost_price")
                    ),
                    output_field=DecimalField(
                        max_digits=12,
                        decimal_places=2
                    )
                )
            )
        )["total"] or 0
    )


    # ==========================================
    # TODAY'S SALES / TRANSACTIONS
    # ==========================================

    today_sales = (
        Sale.objects
        .filter(
            date__gte=start_of_day,
            date__lt=end_of_day
        )
        .select_related("processed_by")
    )

    total_transactions = today_sales.count()


    # ==========================================
    # WHO SOLD WHAT
    # ==========================================

    sales_activity = []

    for sale in today_sales:

        items = sale.items.select_related("product")

        for item in items:

            sales_activity.append({
                "user": (
                    sale.processed_by.username
                    if sale.processed_by
                    else "Unknown"
                ),
                "product": item.product.name,
                "quantity": item.quantity,
                "subtotal": float(item.subtotal),
                "sale_id": sale.id,
            })


    # ==========================================
    # TODAY'S ACTIVITY LOGS
    # ==========================================

    today_activities = (
        ActivityLog.objects
        .filter(
            timestamp__gte=start_of_day,
            timestamp__lt=end_of_day
        )
        .select_related("user")
        .order_by("timestamp")
    )


    # ==========================================
    # LOGIN ACTIVITIES
    # ==========================================

    login_activities = [
        {
            "user": (
                activity.user.username
                if activity.user
                else "Unknown"
            ),
            "action": activity.action,
            "description": activity.description,
            "timestamp": activity.timestamp.isoformat(),
        }
        for activity in today_activities.filter(
            action="LOGIN"
        )
    ]


    # ==========================================
    # STOCK IN ACTIVITIES
    # ==========================================

    stock_in_activities = [
        {
            "user": (
                activity.user.username
                if activity.user
                else "Unknown"
            ),
            "action": activity.action,
            "description": activity.description,
            "timestamp": activity.timestamp.isoformat()
        }
        for activity in today_activities.filter(
            action="STOCK_IN"
        )
    ]


    # ==========================================
    # STOCK OUT ACTIVITIES
    # ==========================================

    stock_out_activities = [
        {
            "user": (
                activity.user.username
                if activity.user
                else "Unknown"
            ),
            "action": activity.action,
            "description": activity.description,
            "timestamp": activity.timestamp.isoformat(),
        }
        for activity in today_activities.filter(
            action="STOCK_OUT"
        )
    ]


    # ==========================================
    # OUT OF STOCK
    # ==========================================

    # CHANGED: quantity=0 -> quantity__lte=0
    # Oversold products (negative quantity, only possible
    # when allow_negative_stock was on) must still count
    # as out of stock for the Telegram bot's answers.

    out_of_stock = products.filter(
        quantity__lte=0
    )

    out_of_stock_products = [
        {
            "name": product.name,
            "quantity": product.quantity,
            "supplier": product.supplier.name,
        }
        for product in out_of_stock
    ]


    # ==========================================
    # LOW STOCK
    # ==========================================

    # CHANGED: hardcoded 5 -> SystemSettings.low_stock_threshold
    # The bot's LOW_STOCK / RESTOCK_NEEDED answers now match
    # whatever threshold is actually configured in Settings,
    # instead of a number that was silently frozen at 5.

    system_settings = SystemSettings.load()

    low_stock = products.filter(
        quantity__gt=0,
        quantity__lte=system_settings.low_stock_threshold
    )

    low_stock_products = [
        {
            "name": product.name,
            "quantity": product.quantity,
            "supplier": product.supplier.name,
        }
        for product in low_stock
    ]


    # ==========================================
    # BEST-SELLING PRODUCTS TODAY
    # ==========================================

    best_selling = (
        today_sale_items
        .values(
            "product__name"
        )
        .annotate(
            units_sold=Sum("quantity")
        )
        .order_by("-units_sold")
    )

    best_selling_products = [
        {
            "name": item["product__name"],
            "units_sold": item["units_sold"],
        }
        for item in best_selling
    ]


    # ==========================================
    # SLOW-SELLING PRODUCTS — LAST 30 DAYS
    # ==========================================

    thirty_days_ago = now - timedelta(days=30)

    slow_selling = (
        Product.objects
        .annotate(
            units_sold_30_days=Coalesce(
                Sum(
                    "sale_items__quantity",
                    filter=Q(
                        sale_items__sale__date__gte=thirty_days_ago,
                        sale_items__sale__date__lt=end_of_day
                    )
                ),
                Value(0)
            )
        )
        .filter(
            units_sold_30_days__lte=5
        )
        .order_by(
            "units_sold_30_days"
        )
    )

    slow_selling_products = [
        {
            "name": product.name,
            "units_sold": product.units_sold_30_days,
        }
        for product in slow_selling
    ]


    # ==========================================
    # ALL PRODUCT INFORMATION
    # ==========================================

    product_data = [
        {
            "name": product.name,
            "sku": product.sku,
            "category": product.category.name,
            "supplier": product.supplier.name,
            "quantity": product.quantity,
            "cost_price": float(product.cost_price),
            "selling_price": float(product.selling_price),
        }
        for product in products
    ]


    # ==========================================
    # ALL SUPPLIER INFORMATION
    # ==========================================

    suppliers = (
        products
        .values(
            "supplier__id",
            "supplier__name",
            "supplier__phone",
            "supplier__email",
            "supplier__address",
        )
        .distinct()
    )

    supplier_data = []

    for supplier in suppliers:

        supplier_products = [
            product.name
            for product in products
            if product.supplier_id == supplier["supplier__id"]
        ]

        supplier_data.append({
            "name": supplier["supplier__name"],
            "phone": supplier["supplier__phone"],
            "email": supplier["supplier__email"],
            "address": supplier["supplier__address"],
            "products": supplier_products,
        })


    # ==========================================
    # RETURN ALL STORE DATA
    # ==========================================

    return {

        "date":
            start_of_day.date().isoformat(),

        # Sales
        "total_revenue":
            float(total_revenue),

        "total_profit":
            float(total_profit),

        "total_units_sold":
            total_units_sold,

        "total_transactions":
            total_transactions,

        # Staff / sales activity
        "sales_activity":
            sales_activity,

        "login_activities":
            login_activities,

        "stock_in_activities":
            stock_in_activities,

        "stock_out_activities":
            stock_out_activities,

        # Inventory
        "out_of_stock_products":
            out_of_stock_products,

        "low_stock_products":
            low_stock_products,

        # Product performance
        "best_selling_products":
            best_selling_products,

        "slow_selling_products":
            slow_selling_products,

        # Products
        "products":
            product_data,

        # Suppliers
        "suppliers":
            supplier_data,
    }




# ==========================================================
# SALES DATA FOR ANY PERIOD
# ==========================================================

def get_sales_period_data(start, end):
    """
    Calculate sales performance between two dates.

    Returns:
    - revenue
    - profit
    - units sold
    - transactions
    """

    sale_items = SaleItem.objects.filter(
        sale__date__gte=start,
        sale__date__lt=end
    )

    revenue = (
        sale_items.aggregate(
            total=Sum("subtotal")
        )["total"] or 0
    )

    units_sold = (
        sale_items.aggregate(
            total=Sum("quantity")
        )["total"] or 0
    )

    profit = (
        sale_items.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") *
                    (
                        F("unit_price") -
                        F("product__cost_price")
                    ),
                    output_field=DecimalField(
                        max_digits=12,
                        decimal_places=2
                    )
                )
            )
        )["total"] or 0
    )

    transactions = (
        Sale.objects.filter(
            date__gte=start,
            date__lt=end
        ).count()
    )

    return {
        "revenue": float(revenue),
        "profit": float(profit),
        "units_sold": int(units_sold),
        "transactions": transactions,
    }


# ==========================================================
# GET SALES PERIOD
# ==========================================================

def get_sales_period(period):
    """
    Return the start and end datetime for a requested period.

    Supported periods:
    - today
    - yesterday
    - week
    - month
    - year
    """

    now = timezone.now()

    today = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    if period == "today":

        start = today
        end = today + timedelta(days=1)

        return start, end

    if period == "yesterday":

        end = today
        start = today - timedelta(days=1)

        return start, end

    if period == "week":

        start = today - timedelta(
            days=today.weekday()
        )

        end = start + timedelta(days=7)

        return start, end

    if period == "month":

        start = today.replace(
            day=1
        )

        if start.month == 12:

            end = start.replace(
                year=start.year + 1,
                month=1
            )

        else:

            end = start.replace(
                month=start.month + 1
            )

        return start, end

    if period == "year":

        start = today.replace(
            month=1,
            day=1
        )

        end = start.replace(
            year=start.year + 1
        )

        return start, end

    return None, None


# ==========================================================
# GET PERIOD SALES SUMMARY
# ==========================================================

def get_period_sales_summary(period):
    """
    Get revenue, profit, units sold, and transactions
    for a requested period.
    """

    start, end = get_sales_period(period)

    if start is None or end is None:
        return None

    data = get_sales_period_data(
        start,
        end
    )

    return {
        "period": period,
        "start": start,
        "end": end,
        "revenue": data["revenue"],
        "profit": data["profit"],
        "units_sold": data["units_sold"],
        "transactions": data["transactions"],
    }


def get_period_activity_data(start, end):
    """
    Same shape as the activity fields already returned by
    get_daily_store_data(), but for any date range instead
    of hardcoded to today.
    """

    period_sales = (
        Sale.objects
        .filter(
            date__gte=start,
            date__lt=end,
        )
        .select_related("processed_by")
    )

    sales_activity = []

    for sale in period_sales:

        items = sale.items.select_related("product")

        for item in items:

            sales_activity.append({
                "user": (
                    sale.processed_by.username
                    if sale.processed_by
                    else "Unknown"
                ),
                "product": item.product.name,
                "quantity": item.quantity,
                "subtotal": float(item.subtotal),
                "sale_id": sale.id,
                "timestamp": sale.date.isoformat(),
            })

    period_activities = (
        ActivityLog.objects
        .filter(
            timestamp__gte=start,
            timestamp__lt=end,
        )
        .select_related("user")
        .order_by("timestamp")
    )

    def _serialize(activities):
        return [
            {
                "user": (
                    activity.user.username
                    if activity.user
                    else "Unknown"
                ),
                "action": activity.action,
                "description": activity.description,
                "timestamp": activity.timestamp.isoformat(),
            }
            for activity in activities
        ]

    login_activities = _serialize(
        period_activities.filter(action="LOGIN")
    )

    stock_in_activities = _serialize(
        period_activities.filter(action="STOCK_IN")
    )

    stock_out_activities = _serialize(
        period_activities.filter(action="STOCK_OUT")
    )

    return {
        "sales_activity": sales_activity,
        "login_activities": login_activities,
        "stock_in_activities": stock_in_activities,
        "stock_out_activities": stock_out_activities,
    }


def get_activity_period_summary(period):
    """
    period: "today" | "yesterday" | "week" | "month" | "year"

    Returns None for an unrecognized period, same contract
    as get_period_sales_summary(), so callers can handle
    both the same way.
    """

    start, end = get_sales_period(period)

    if start is None or end is None:
        return None

    return get_period_activity_data(start, end)
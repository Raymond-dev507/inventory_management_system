from .models import Product, SystemSettings


def notifications(request):
    """
    Makes notif_count, notif_out_of_stock, and notif_low_stock
    available in every template automatically.

    Respects the notification toggles in SystemSettings:
    - If out_of_stock_notifications is off, out-of-stock
      products are excluded from the bell entirely.
    - If low_stock_notifications is off, low-stock products
      are excluded from the bell entirely.

    Nothing is stored — this is computed fresh on every
    request, so the count is always accurate and clears
    itself the moment a product is restocked.
    """

    if not request.user.is_authenticated:
        return {}

    settings_obj = SystemSettings.load()

    out_of_stock_products = []
    low_stock_products = []

    if settings_obj.out_of_stock_notifications:
        out_of_stock_products = list(
            Product.objects.filter(quantity__lte=0).order_by("name")
        )

    if settings_obj.low_stock_notifications:
        low_stock_products = list(
            Product.objects.filter(
                quantity__gt=0,
                quantity__lte=settings_obj.low_stock_threshold,
            ).order_by("quantity")
        )

    notif_count = len(out_of_stock_products) + len(low_stock_products)

    return {
        "notif_out_of_stock": out_of_stock_products,
        "notif_low_stock": low_stock_products,
        "notif_count": notif_count,
    }


def display_settings(request):
    """
    Makes currency_symbol and format strings available in
    every template automatically, so templates never need
    to hardcode ₦ or a specific date/time format again.

    Usage in templates:

        {{ currency_symbol }}{{ amount }}

        {{ sale.date|date:date_format_str }}
        {{ sale.date|date:time_format_str }}
        {{ sale.date|date:datetime_format_str }}
    """

    if not request.user.is_authenticated:

        # Sensible fallback so templates never break
        # for logged-out pages (e.g. login screen).

        return {
            "currency_symbol": "₦",
            "date_format_str": "d/m/Y",
            "time_format_str": "g:i A",
            "datetime_format_str": "d/m/Y g:i A",
        }

    settings_obj = SystemSettings.load()

    # settings_obj.date_format is already stored using Django's
    # own date-filter format characters (d/m/Y, m/d/Y, Y-m-d),
    # so it can be passed straight into the |date: filter.

    if settings_obj.time_format == "24":
        time_format_str = "H:i"
    else:
        time_format_str = "g:i A"

    return {
        "currency_symbol": settings_obj.currency,
        "date_format_str": settings_obj.date_format,
        "time_format_str": time_format_str,
        "datetime_format_str": f"{settings_obj.date_format} {time_format_str}",
    }
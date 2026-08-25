from django.contrib.auth.decorators import login_required
from django.shortcuts import render,HttpResponse

from .models import Product, Sale, SaleItem, SystemSettings
from django.db.models import Sum, F, DecimalField, ExpressionWrapper

from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models.functions import TruncDate
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)



def get_report_data(request):

    # Start with all sale items
    sale_items = SaleItem.objects.all()

    # Selected preset period
    period = request.GET.get("period", "all")

    date_error = None

    # Custom dates
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    now = timezone.now()


    # =====================================================
    # PRESET PERIODS
    # =====================================================

    if period == "today":

        start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        sale_items = sale_items.filter(
            sale__date__gte=start
        )


    elif period == "week":

        start = now - timedelta(
            days=now.weekday()
        )

        start = start.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        sale_items = sale_items.filter(
            sale__date__gte=start
        )


    elif period == "month":

        start = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        sale_items = sale_items.filter(
            sale__date__gte=start
        )


    elif period == "year":

        start = now.replace(
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        sale_items = sale_items.filter(
            sale__date__gte=start
        )


    # =====================================================
    # CUSTOM DATE RANGE
    # =====================================================

    elif period == "custom" and start_date and end_date:

        try:

            start = datetime.strptime(
                start_date,
                "%Y-%m-%d"
            )

            end = datetime.strptime(
                end_date,
                "%Y-%m-%d"
            )


            # Check if To date is before From date

            if end < start:

                date_error = (
                    "Invalid date range. "
                    "The 'To' date cannot be earlier "
                    "than the 'From' date."
                )


            else:

                # Make dates timezone-aware

                start = timezone.make_aware(
                    start
                )


                # Include entire ending day

                end = timezone.make_aware(
                    end.replace(
                        hour=23,
                        minute=59,
                        second=59
                    )
                )


                sale_items = sale_items.filter(
                    sale__date__gte=start,
                    sale__date__lte=end
                )


        except ValueError:

            date_error = "Please enter valid dates."


    # =====================================================
    # TOTAL UNITS SOLD
    # =====================================================

    total_units_sold = (
        sale_items.aggregate(
            total=Sum("quantity")
        )["total"] or 0
    )


    # =====================================================
    # TOTAL REVENUE
    # =====================================================

    total_revenue = (
        sale_items.aggregate(
            total=Sum("subtotal")
        )["total"] or 0
    )


    # =====================================================
    # TOTAL PROFIT
    # =====================================================

    total_profit = (
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


    # =====================================================
    # DIFFERENT PRODUCTS SOLD
    # =====================================================

    products_sold = (
        sale_items
        .values("product")
        .distinct()
        .count()
    )


    # =====================================================
    # PRODUCT SALES BREAKDOWN
    # =====================================================

    product_sales = (
        sale_items
        .values(
            "product__name"
        )
        .annotate(

            units_sold=Sum(
                "quantity"
            ),

            revenue=Sum(
                "subtotal"
            ),

            profit=Sum(
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
        )
        .order_by("-units_sold")
    )


    # =====================================================
    # RETURN REPORT DATA
    # =====================================================

    return {

        "total_units_sold":
            total_units_sold,

        "total_revenue":
            total_revenue,

        "total_profit":
            total_profit,

        "products_sold":
            products_sold,

        "selected_period":
            period,

        "start_date":
            start_date,

        "end_date":
            end_date,

        "date_error":
            date_error,

        "product_sales":
            product_sales,

    }


# =========================================================
# REPORT PAGE
# =========================================================

@login_required
def reports(request):

    context = get_report_data(request)

    return render(
        request,
        "reports.html",
        context
    )


# =========================================================
# EXPORT SALES PDF
# =========================================================

@login_required
def export_sales_pdf(request):

    # Get exactly the same report data
    # used by the Reports page

    data = get_report_data(request)

    system_settings = SystemSettings.load()
    currency = system_settings.currency


    # If the date range is invalid,
    # don't generate a misleading PDF

    if data["date_error"]:

        return HttpResponse(
            data["date_error"],
            status=400
        )


    # =====================================================
    # CREATE PDF RESPONSE
    # =====================================================

    response = HttpResponse(
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        'attachment; filename="sales_report.pdf"'
    )


    # =====================================================
    # PDF DOCUMENT
    # =====================================================

    document = SimpleDocTemplate(
        response,
        pagesize=A4,

        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )


    styles = getSampleStyleSheet()


    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=20,
        spaceAfter=6,
    )


    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=10,
        spaceAfter=4,
    )


    contact_style = ParagraphStyle(
        "ReportContact",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        textColor=colors.grey,
        spaceAfter=20,
    )


    elements = []


    # =====================================================
    # TITLE — now pulled from Settings instead of hardcoded
    # =====================================================

    elements.append(
        Paragraph(
            system_settings.business_name.upper(),
            title_style
        )
    )


    elements.append(
        Paragraph(
            "Sales Report",
            subtitle_style
        )
    )


    # =====================================================
    # BUSINESS CONTACT LINE (address / phone / email)
    # Only shown if at least one is filled in.
    # =====================================================

    contact_parts = []

    if system_settings.address:
        contact_parts.append(system_settings.address)

    if system_settings.phone:
        contact_parts.append(system_settings.phone)

    if system_settings.email:
        contact_parts.append(system_settings.email)

    if contact_parts:

        elements.append(
            Paragraph(
                " &nbsp;&middot;&nbsp; ".join(contact_parts),
                contact_style
            )
        )

    else:

        elements.append(
            Spacer(1, 14)
        )


    # =====================================================
    # PERIOD
    # =====================================================

    period = data["selected_period"]

    if period == "custom":

        report_period = (
            f"{data['start_date']} "
            f"to "
            f"{data['end_date']}"
        )

    else:

        period_names = {
            "all": "All Time",
            "today": "Today",
            "week": "This Week",
            "month": "This Month",
            "year": "This Year",
        }

        report_period = period_names.get(
            period,
            "All Time"
        )


    elements.append(
        Paragraph(
            f"<b>Report Period:</b> {report_period}",
            styles["Normal"]
        )
    )

    elements.append(
        Spacer(1, 20)
    )


    # =====================================================
    # SUMMARY — currency now pulled from Settings
    # =====================================================

    summary_data = [

        [
            "Total Revenue",
            "Total Profit",
            "Units Sold",
            "Products Sold",
        ],

        [
            f"{currency}{data['total_revenue']:,.2f}",
            f"{currency}{data['total_profit']:,.2f}",
            str(data["total_units_sold"]),
            str(data["products_sold"]),
        ]

    ]


    summary_table = Table(
        summary_data,
        colWidths=[
            130,
            130,
            100,
            100,
        ]
    )


    summary_table.setStyle(
        TableStyle([

            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#0d6efd")
            ),

            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),

            (
                "ALIGN",
                (0, 0),
                (-1, -1),
                "CENTER"
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),

            (
                "FONTNAME",
                (0, 1),
                (-1, 1),
                "Helvetica-Bold"
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                10
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                10
            ),

        ])
    )


    elements.append(
        summary_table
    )

    elements.append(
        Spacer(1, 25)
    )


    # =====================================================
    # PRODUCT SALES
    # =====================================================

    elements.append(
        Paragraph(
            "Product Sales Breakdown",
            styles["Heading2"]
        )
    )

    elements.append(
        Spacer(1, 10)
    )


    product_table_data = [

        [
            "Product",
            "Units Sold",
            "Revenue",
            "Profit",
        ]

    ]


    for product in data["product_sales"]:

        product_table_data.append([

            product["product__name"],

            str(
                product["units_sold"]
            ),

            f"{currency}{product['revenue']:,.2f}",

            f"{currency}{product['profit']:,.2f}",

        ])


    if len(product_table_data) == 1:

        product_table_data.append([
            "No sales found",
            "-",
            "-",
            "-",
        ])


    product_table = Table(
        product_table_data,
        colWidths=[
            190,
            80,
            100,
            100,
        ]
    )


    product_table.setStyle(
        TableStyle([

            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#0d6efd")
            ),

            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "ALIGN",
                (1, 1),
                (-1, -1),
                "RIGHT"
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                8
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                8
            ),

        ])
    )


    elements.append(
        product_table
    )


    # =====================================================
    # BUILD PDF
    # =====================================================

    document.build(
        elements
    )


    return response
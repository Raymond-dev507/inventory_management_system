from datetime import timedelta
from django.conf import settings
import resend
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum, Q, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .Telegram import send_telegram_message
from .models import Category, Supplier, Product, StockIn, StockOut, Sale, SaleItem, ActivityLog, SystemSettings
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

# Create your views here.



def dashboard(request):
    system_settings = SystemSettings.load()

    total_categories = Category.objects.count()
    total_suppliers = Supplier.objects.count()
    total_products = Product.objects.count()

    total_stock = Product.objects.aggregate(total=Sum("quantity"))["total"] or 0

    recent_products = Product.objects.order_by("-created_at")[:5]

    # CHANGED: quantity=0 -> quantity__lte=0
    # A product with negative quantity (oversold while
    # allow_negative_stock was on) must still count as
    # out of stock, not silently disappear from this list.
    out_of_stock = Product.objects.filter(
        quantity__lte=0
    ).order_by("name")[:5]

    low_stock = Product.objects.filter(
        quantity__gt=0,
        quantity__lte=system_settings.low_stock_threshold
    ).order_by("quantity")[:5]

    best_selling = (
        SaleItem.objects
        .values("product__name")
        .annotate(
            units_sold=Sum("quantity")
        )
        .filter(
            units_sold__gt=5
        )
        .order_by("-units_sold")[:5]
    )

    thirty_days_ago = timezone.now() - timedelta(days=30)

    slow_selling = (
        Product.objects
        .filter(
            quantity__gt=0
        )
        .annotate(
            units_sold=Coalesce(
                Sum(
                    "sale_items__quantity",
                    filter=Q(
                        sale_items__sale__date__gte=thirty_days_ago
                    )
                ),
                Value(0)
            )
        )
        .filter(
            quantity__gt=0,
            units_sold__lte=5
        )
        .order_by("units_sold")[:5]
    )

    inventory_insights = []

    if out_of_stock.exists():

        out_of_stock_products = list(out_of_stock)

        product_names = ", ".join(
            product.name
            for product in out_of_stock_products
        )

        if len(out_of_stock_products) == 1:
            message = (
                f"{product_names} is out of stock and needs "
                f"immediate restocking."
            )
        else:
            message = (
                f"{product_names} are out of stock and need "
                f"immediate restocking."
            )

        inventory_insights.append({
            "type": "danger",
            "icon": "bi-exclamation-triangle",
            "title": "Restocking Required",
            "message": message
        })

    if low_stock.exists():

        low_stock_products = list(low_stock)

        product_names = ", ".join(
            product.name
            for product in low_stock_products
        )

        if len(low_stock_products) == 1:
            product = low_stock_products[0]

            message = (
                f"{product.name} has only {product.quantity} "
                f"unit(s) remaining. Consider restocking soon."
            )

        else:
            message = (
                f"{product_names} are running low on stock. "
                f"Consider restocking these products soon."
            )

        inventory_insights.append({
            "type": "warning",
            "icon": "bi-box-seam",
            "title": "Low Stock",
            "message": message
        })

    if best_selling:

        highest_sales = best_selling[0]["units_sold"]

        top_products = [
            product
            for product in best_selling
            if product["units_sold"] == highest_sales
        ]

        product_names = [
            product["product__name"]
            for product in top_products
        ]

        if len(product_names) == 1:

            message = (
                f"{product_names[0]} is your best-selling product "
                f"with {highest_sales} units sold."
            )

        elif len(product_names) == 2:

            message = (
                f"{product_names[0]} and {product_names[1]} are your "
                f"best-selling products with {highest_sales} "
                f"units sold each."
            )

        else:

            names = ", ".join(product_names[:-1])
            last_name = product_names[-1]

            message = (
                f"{names}, and {last_name} are your best-selling "
                f"products with {highest_sales} units sold each."
            )

        inventory_insights.append({
            "type": "success",
            "icon": "bi-fire",
            "title": "Best Seller",
            "message": message
        })

    if slow_selling.exists():

        slow_products = list(slow_selling)

        no_sales_products = [
            product
            for product in slow_products
            if product.units_sold == 0
        ]

        low_sales_products = [
            product
            for product in slow_products
            if product.units_sold > 0
        ]

        slow_messages = []

        if no_sales_products:

            no_sales_names = [
                product.name
                for product in no_sales_products
            ]

            if len(no_sales_names) == 1:

                slow_messages.append(
                    f"{no_sales_names[0]} has no sales "
                    f"in the last 30 days."
                )

            elif len(no_sales_names) == 2:

                slow_messages.append(
                    f"{no_sales_names[0]} and {no_sales_names[1]} "
                    f"have no sales in the last 30 days."
                )

            else:

                names = ", ".join(no_sales_names[:-1])
                last_name = no_sales_names[-1]

                slow_messages.append(
                    f"{names}, and {last_name} have no sales "
                    f"in the last 30 days."
                )

        if low_sales_products:

            low_sales_details = [
                f"{product.name} ({product.units_sold} sold)"
                for product in low_sales_products
            ]

            if len(low_sales_details) == 1:

                slow_messages.append(
                    f"{low_sales_details[0]} has low sales "
                    f"in the last 30 days."
                )

            elif len(low_sales_details) == 2:

                slow_messages.append(
                    f"{low_sales_details[0]} and "
                    f"{low_sales_details[1]} have low sales "
                    f"in the last 30 days."
                )

            else:

                names = ", ".join(low_sales_details[:-1])
                last_name = low_sales_details[-1]

                slow_messages.append(
                    f"{names}, and {last_name} have low sales "
                    f"in the last 30 days."
                )

        message = " ".join(slow_messages)

        inventory_insights.append({
            "type": "info",
            "icon": "bi-graph-down",
            "title": "Slow Sales",
            "message": message
        })

    else:

        inventory_insights.append({
            "type": "success",
            "icon": "bi-check-circle",
            "title": "Sales Performance",
            "message": (
                "Your products are showing healthy sales activity. "
                "No slow-selling products were detected in the "
                "last 30 days."
            )
        })

    return render(request, 'dashboard.html',context={
        'total_categories':total_categories,
        'total_suppliers':total_suppliers,
        'total_products':total_products,
        "total_stock": total_stock,
        "recent_products": recent_products,

        "out_of_stock": out_of_stock,
        "low_stock": low_stock,

        "best_selling": best_selling,
        "slow_selling": slow_selling,
        "inventory_insights": inventory_insights,
         })


@permission_required("inventory.add_category", raise_exception=True)
@transaction.atomic
def category(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        cate=Category(name=name,description=description)
        cate.save()
        return redirect("all_categories")

    else:
        return render(request,'cateinput.html')

@permission_required("inventory.view_category", raise_exception=True)
@transaction.atomic
def all_categories(request):
    categories = Category.objects.all()
    total_categories = Category.objects.count()

    return render(request, 'all_categories.html', {
        'categories': categories,
        'total_categories': total_categories,
    })
@permission_required("inventory.delete_category", raise_exception=True)
@transaction.atomic
def remove_category(request,id):
    remove_category = Category.objects.get(id=id)
    remove_category.delete()
    messages.success(request, "Category deleted successfully.")
    return redirect("all_categories")

@permission_required("inventory.add_product", raise_exception=True)
def edit_category(request,id):
    edit_category = Category.objects.get(id=id)
    return render(request, 'edit.html', context={'edit':edit_category})

@permission_required("inventory.change_category", raise_exception=True)
def update_category(request, id):
    category = get_object_or_404(Category, id=id)

    if request.method == "POST":
        category.name = request.POST.get("name")
        category.description = request.POST.get("description")
        category.save()

        messages.success(request, "Category updated successfully.")
        return redirect("all_categories")


@permission_required("inventory.add_supplier", raise_exception=True)
@transaction.atomic
def supplier(request):
    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone")
        email = request.POST.get("email")
        address = request.POST.get("address")
        supplier = Supplier(name=name, phone=phone, email=email, address=address)
        supplier.save()

        if email:
            subject = f"Welcome to Stomachache Company, {name}"

            message = f"""Hello {name},

Welcome to Stomachache Company.

Your supplier account has been successfully created.

Supplier ID: {supplier.id}
Phone: {phone}
Address: {address}

Thank you for partnering with us.

Best regards,
SoftCode Company"""

            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = settings.BREVO_API_KEY

            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
                sib_api_v3_sdk.ApiClient(configuration)
            )

            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": email, "name": name}],
                sender={"email": "lolyboy113@gmail.com", "name": "SoftCode Company"},
                subject=subject,
                text_content=message,
            )

            try:
                api_instance.send_transac_email(send_smtp_email)
            except ApiException as e:
                print(f"Brevo API error: {e}")

        return redirect("all_supplier")

    return render(request, "suplier.html")


def all_supplier(request):
    suppliers = Supplier.objects.all()
    total_suppliers = Supplier.objects.count()
    return render(request, 'all_supplier.html', context={
        'suppliers': suppliers,
        'total_suppliers': total_suppliers
          })

@permission_required("inventory.change_supplier", raise_exception=True)
def edit_supplier(request,id):
    edit_supplier = Supplier.objects.get(id=id)
    return render(request, 'edit_supplier.html', context={'edit':edit_supplier})


def update_supplier(request,id):
    supplier = get_object_or_404(Supplier, id=id)
    if request.method == "POST":
        supplier.name = request.POST.get("name")
        supplier.phone = request.POST.get("phone")
        supplier.email = request.POST.get("email")
        supplier.address = request.POST.get("address")
        supplier.save()
        messages.success(request, "Supplier updated successfully.")
        return redirect("all_supplier")


@permission_required("inventory.delete_supplier", raise_exception=True)
def remove_supplier(request,id):
    remove=Supplier.objects.get(id=id)
    remove.delete()
    messages.success(request, "Supplier deleted successfully.")
    return redirect("all_supplier")



@permission_required("inventory.add_product", raise_exception=True)
@transaction.atomic
def product(request):
    if request.method == "POST":
        category_id = request.POST.get("category")
        supplier_id = request.POST.get("supplier")
        name = request.POST.get("name")
        sku = request.POST.get("sku")
        cost_price = request.POST.get("cost_price")
        selling_price = request.POST.get("selling_price")
        description = request.POST.get("description")
        quantity = request.POST.get("quantity")


        if not all([category_id, supplier_id, name, sku, cost_price, selling_price, quantity]):
            messages.error(request, "Please fill in all required fields.")
            return redirect("product")


        if Product.objects.filter(sku=sku).exists():
            messages.error(request, "This SKU already exists.")
            return redirect("product")

        try:
            product = Product(
                category=Category.objects.get(id=category_id),
                supplier=Supplier.objects.get(id=supplier_id),
                name=name,
                sku=sku,
                cost_price=cost_price,
                selling_price=selling_price,
                description=description,
                quantity=quantity,
            )

            product.save()

            messages.success(request, "Product added successfully.")
            return redirect("all_product")

        except Exception:
            messages.error(request, "An error occurred while saving the product.")
            return redirect("product")

    return render(request, "product.html", {
        "category": Category.objects.all(),
        "supplier": Supplier.objects.all(),
    })
@permission_required("inventory.view_product", raise_exception=True)
def all_product(request):
    products=Product.objects.all()
    total_products = Product.objects.count()
    return render(request, 'all_product.html', context={
        'products': products,
        'total_products': total_products
    })
@permission_required("inventory.change_product", raise_exception=True)
def edit_product(request,id):
    edit_product = Product.objects.get(id=id)

    category = Category.objects.all()
    supplier = Supplier.objects.all()
    return render(request, 'edit_product.html', context={
        'edit':edit_product,
        'category': category,
        'supplier': supplier
         })

@permission_required("inventory.change_product", raise_exception=True)
def update_product(request,id):
    product=Product.objects.get(id=id)
    if request.method == "POST":
        product.category = Category.objects.get(id=request.POST.get("category"))
        product.supplier = Supplier.objects.get(id=request.POST.get("supplier"))

        product.name = request.POST.get("name")
        product.sku = request.POST.get("sku")
        product.cost_price = request.POST.get("cost_price")
        product.selling_price = request.POST.get("selling_price")
        product.description = request.POST.get("description")
        product.quantity = request.POST.get("quantity")
        product.save()
        messages.success(
            request,
            f"Product '{product.name}' updated successfully."
        )
        return redirect("all_product")

@permission_required("inventory.delete_product", raise_exception=True)
def remove_product(request,id):
    product = get_object_or_404(Product, id=id)
    product.delete()
    ActivityLog.objects.create(
        user=request.user,
        action="DELETE PRODUCT",
        description=(
            f"Completed Delete Product #{product.id} "
            f"Name of the product{product.name}"
        )
    )
    messages.success(request, "Product deleted successfully.")
    return redirect("all_product")

@permission_required("inventory.add_product", raise_exception=True)
@login_required
def add_stock(request):

    products = Product.objects.all()

    if request.method == "POST":

        product_id = request.POST.get("product")
        quantity = int(request.POST.get("quantity"))

        product = get_object_or_404(
            Product,
            id=product_id
        )

        StockIn.objects.create(
            product=product,
            quantity=quantity
        )

        product.quantity += quantity
        product.save()

        ActivityLog.objects.create(
            user=request.user,
            action="STOCK_IN",
            description=(
                f"Added {quantity} units of "
                f"{product.name} to stock."
            )
        )

        return redirect("stock_list")

    return render(
        request,
        "add_stock.html",
        {
            "products": products
        }
    )

def stock_list(request):
    stocks = StockIn.objects.all().order_by("-date")

    return render(request, "stock_list.html", {
        "stocks": stocks
    })


@permission_required("inventory.add_product", raise_exception=True)
@login_required
@transaction.atomic
def stock_out(request):

    products = Product.objects.all()

    if request.method == "POST":

        product_id = request.POST.get("product")
        quantity = int(request.POST.get("quantity"))
        reason = request.POST.get("reason")
        note = request.POST.get("note")

        product = get_object_or_404(Product, id=product_id)


        if quantity > product.quantity:
            return render(request, "add_stock_out.html", {
                "products": products,
                "error": "Not enough stock available."
            })


        StockOut.objects.create(
            product=product,
            quantity=quantity,
            reason=reason,
            note=note,
            processed_by = request.user
        )


        product.quantity -= quantity
        product.save()

        ActivityLog.objects.create(
            user=request.user,
            action="STOCK_OUT",
            description=(
                f"Removed {quantity} units of "
                f"{product.name} from stock. "
                f"Reason: {reason}."
            )
        )

        return redirect("stock_out_list")

    return render(request, "stock_out.html", {
        "products": products,
        "reasons": StockOut.REASON_CHOICES,
    })

def stock_out_list(request):
    stock_out = StockOut.objects.all().order_by("-date")
    return render(request, "stock_out_list.html", context={'stock_out': stock_out})


@login_required
@permission_required("inventory.add_sale", raise_exception=True)
def create_sale(request):

    system_settings = SystemSettings.load()

    products = Product.objects.all()
    cart = request.session.get("cart", {})

    if request.method == "POST":

        product_id = request.POST.get("product")
        quantity = request.POST.get("quantity")

        if not product_id:
            messages.error(request, "Please select a product.")
            return redirect("create_sale")

        if not quantity:
            messages.error(request, "Please enter quantity.")
            return redirect("create_sale")

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            messages.error(request, "Quantity must be an integer.")
            return redirect("create_sale")

        if quantity <= 0:
            messages.error(request, "Quantity must be greater than zero.")
            return redirect("create_sale")

        product = get_object_or_404(Product, id=product_id)
        product_id = str(product_id)

        existing_quantity = cart.get(product_id, 0)

        if not system_settings.allow_negative_stock:

            if existing_quantity + quantity > product.quantity:

                messages.error(
                    request,
                    f"Only {product.quantity} "
                    f"{product.name} available."
                )

                return redirect("create_sale")

        if product_id in cart:
            cart[product_id] += quantity
        else:
            cart[product_id] = quantity

        request.session["cart"] = cart
        request.session.modified = True

        return redirect("create_sale")

    cart_items, total = get_cart_items(cart)

    return render(
        request,
        "create_sale.html",
        {
            "products": products,
            "cart_items": cart_items,
            "total": total,
            'payment_methods': Sale.PAYMENT_METHODS,
        }
    )

def get_cart_items(cart):
    cart_items = []
    total = 0

    for product_id, quantity in cart.items():

        product = get_object_or_404(
            Product,
            id=product_id
        )

        subtotal = product.selling_price * quantity

        total += subtotal

        cart_items.append({
            "product": product,
            "quantity": quantity,
            "unit_price": product.selling_price,
            "subtotal": subtotal,
        })

    return cart_items, total



@login_required
def remove_from_cart(request, product_id):

    cart = request.session.get("cart", {})

    product_id = str(product_id)

    if product_id in cart:
        del cart[product_id]

    request.session["cart"] = cart
    request.session.modified = True

    return redirect("create_sale")




@login_required
def increase_quantity(request, product_id):

    cart = request.session.get("cart", {})

    product_id = str(product_id)

    product = get_object_or_404(
        Product,
        id=product_id
    )

    if product_id in cart:

        if cart[product_id] < product.quantity:
            cart[product_id] += 1

        else:
            messages.error(
                request,
                f"Only {product.quantity} {product.name} available."
            )

    request.session["cart"] = cart
    request.session.modified = True

    return redirect("create_sale")


@login_required
def decrease_quantity(request, product_id):

    cart = request.session.get("cart", {})

    product_id = str(product_id)

    if product_id in cart:

        cart[product_id] -= 1

        if cart[product_id] <= 0:
            del cart[product_id]

    request.session["cart"] = cart
    request.session.modified = True

    return redirect("create_sale")


@login_required
def clear_cart(request):

    request.session["cart"] = {}
    request.session.modified = True

    return redirect("create_sale")


@login_required
@permission_required("inventory.add_sale", raise_exception=True)
def complete_sale(request):

    system_settings = SystemSettings.load()

    cart = request.session.get("cart", {})

    if not cart:
        messages.error(
            request,
            "There are no products in the cart."
        )
        return redirect("create_sale")

    if request.method != "POST":
        return redirect("create_sale")

    customer_name = request.POST.get("customer_name", "").strip()
    payment_method = request.POST.get("payment_method")

    # --------------------------------------------------
    # VALIDATE PAYMENT METHOD
    # --------------------------------------------------

    valid_payment_methods = dict(Sale.PAYMENT_METHODS)

    if payment_method not in valid_payment_methods:
        messages.error(
            request,
            "Please select a valid payment method."
        )
        return redirect("create_sale")

    # --------------------------------------------------
    # COMPLETE SALE
    # --------------------------------------------------

    try:

        with transaction.atomic():

            # ------------------------------------------
            # LOCK PRODUCTS
            # ------------------------------------------
            #
            # select_for_update() locks the product rows
            # until this transaction finishes.
            #
            # This prevents two simultaneous sales from
            # changing the same stock incorrectly.
            # ------------------------------------------

            product_ids = [int(product_id) for product_id in cart.keys()]

            locked_products = (
                Product.objects
                .select_for_update()
                .filter(id__in=product_ids)
            )

            products_by_id = {
                str(product.id): product
                for product in locked_products
            }

            # Make sure every product still exists
            for product_id in cart:

                if product_id not in products_by_id:
                    raise ValueError(
                        f"Product with ID {product_id} no longer exists."
                    )

            # ------------------------------------------
            # BUILD SALE ITEMS USING LOCKED PRODUCTS
            # ------------------------------------------

            sale_items = []
            total = 0
            low_stock_products = []

            for product_id, quantity in cart.items():

                product = products_by_id[product_id]

                # Make sure quantity is valid
                if not isinstance(quantity, int) or quantity <= 0:
                    raise ValueError(
                        f"Invalid quantity for {product.name}."
                    )

                # --------------------------------------
                # CHECK CURRENT DATABASE STOCK
                # --------------------------------------

                if not system_settings.allow_negative_stock:

                    if quantity > product.quantity:

                        raise ValueError(
                            f"Only {product.quantity} "
                            f"{product.name} available."
                        )

                unit_price = product.selling_price
                subtotal = unit_price * quantity

                total += subtotal

                # --------------------------------------
                # SHOULD STOCK BE DEDUCTED?
                # --------------------------------------

                stock_was_deducted = (
                    system_settings.auto_deduct_stock
                )

                sale_items.append({
                    "product": product,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "subtotal": subtotal,
                    "stock_deducted": stock_was_deducted,
                })

            # ------------------------------------------
            # CREATE SALE
            # ------------------------------------------

            sale = Sale.objects.create(
                customer_name=customer_name,
                total_amount=total,
                payment_method=payment_method,
                processed_by=request.user,
            )

            # ------------------------------------------
            # CREATE SALE ITEMS + DEDUCT STOCK
            # ------------------------------------------

            for item in sale_items:

                product = item["product"]

                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    subtotal=item["subtotal"],
                    stock_deducted=item["stock_deducted"],
                )

                # --------------------------------------
                # AUTO DEDUCT STOCK
                # --------------------------------------

                if item["stock_deducted"]:

                    product.quantity -= item["quantity"]

                    product.save(
                        update_fields=["quantity"]
                    )

                    # Don't send Telegram here.
                    #
                    # Just remember that this product
                    # needs a notification.
                    if (
                        system_settings.low_stock_notifications
                        and product.quantity
                        <= system_settings.low_stock_threshold
                    ):
                        low_stock_products.append(
                            {
                                "name": product.name,
                                "quantity": product.quantity,
                            }
                        )

        # --------------------------------------------------
        # TRANSACTION SUCCESSFULLY COMMITTED
        # --------------------------------------------------
        #
        # Telegram happens AFTER the database transaction.
        # Therefore Telegram cannot interfere with the
        # database transaction or hold database locks.
        # --------------------------------------------------

        for item in low_stock_products:

            send_telegram_message(
                f"⚠️ {item['name']} is low on stock: "
                f"{item['quantity']} left."
            )

    except ValueError as error:

        messages.error(
            request,
            str(error)
        )

        return redirect("create_sale")

    # --------------------------------------------------
    # CLEAR CART
    # --------------------------------------------------

    request.session["cart"] = {}
    request.session.modified = True

    # --------------------------------------------------
    # ACTIVITY LOG
    # --------------------------------------------------

    ActivityLog.objects.create(
        user=request.user,
        action="SALE",
        description=(
            f"Completed sale #{sale.id} "
            f"for ₦{total:,.2f}"
        )
    )

    # --------------------------------------------------
    # SUCCESS MESSAGE
    # --------------------------------------------------

    messages.success(
        request,
        "Sale completed successfully."
    )

    # --------------------------------------------------
    # RECEIPT
    # --------------------------------------------------

    return redirect(
        "sale_receipt",
           sale_id=sale.id
    )


@login_required
def sale_receipt(request, sale_id):

    sale = get_object_or_404(Sale, id=sale_id)
    system_settings = SystemSettings.load()

    return render(request, "receipt.html", {
        "sale": sale,
        "settings": system_settings,
    })


# =========================================================
# STOCK CATCH-UP
#
# Called from settings_view (in user.py) whenever
# auto_deduct_stock is toggled from False -> True.
#
# Finds every SaleItem that was created while auto-deduct
# was off (stock_deducted=False) and deducts its stock now,
# then marks it as caught up so it's never processed twice.
# =========================================================

def catch_up_stock_deduction():

    with transaction.atomic():

        pending_items = (
            SaleItem.objects
            .select_for_update()
            .select_related("product")
            .filter(stock_deducted=False)
        )

        caught_up_items = []

        for item in pending_items:

            product = (
                Product.objects
                .select_for_update()
                .get(id=item.product_id)
            )

            old_stock = product.quantity

            product.quantity -= item.quantity

            product.save(
                update_fields=["quantity"]
            )

            item.stock_deducted = True

            item.save(
                update_fields=["stock_deducted"]
            )

            caught_up_items.append({
                "product_name": product.name,
                "quantity": item.quantity,
                "old_stock": old_stock,
                "new_stock": product.quantity,
            })

    return caught_up_items


def global_search(request):

    query = request.GET.get('q', '').strip()

    products = Product.objects.none()
    stock_ins = StockIn.objects.none()
    stock_outs = StockOut.objects.none()
    sales = Sale.objects.none()

    if query:

        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query)
        )

        stock_ins = StockIn.objects.filter(
            Q(product__name__icontains=query) |
            Q(product__sku__icontains=query)
        )

        stock_outs = StockOut.objects.filter(
            Q(product__name__icontains=query) |
            Q(product__sku__icontains=query)
        )

        sales = Sale.objects.filter(
            Q(items__product__name__icontains=query) |
            Q(items__product__sku__icontains=query) |
            Q(customer_name__icontains=query) |
            Q(payment_method__icontains=query) |
            Q(processed_by__username__icontains=query)
        ).distinct()

        for sale in sales:

            sale_match = (
                query.lower() in (sale.customer_name or "").lower()
                or query.lower() in sale.payment_method.lower()
                or (
                    sale.processed_by
                    and query.lower() in sale.processed_by.username.lower()
                )
            )

            matching_items = sale.items.filter(
                Q(product__name__icontains=query) |
                Q(product__sku__icontains=query)
            )

            if sale_match:

                sale.search_items = sale.items.all()
                sale.search_total = sale.total_amount

            else:

                sale.search_items = matching_items

                sale.search_total = sum(
                    item.subtotal for item in matching_items
                )

    return render(request, 'search.html', {
        'query': query,
        'products': products,
        'stock_ins': stock_ins,
        'stock_outs': stock_outs,
        'sales': sales,
    })


@permission_required("inventory.view_sale", raise_exception=True)
def sale_records(request):
    sales = Sale.objects.select_related("processed_by").prefetch_related("items__product").order_by("-date")
    total_sales = sales.count()

    cash_sales = sales.filter(
        payment_method="cash"
    ).count()

    transfer_sales = sales.filter(
        payment_method="transfer"
    ).count()

    pos_sales = sales.filter(
        payment_method="pos"
    ).count()
    return render(request, "sale_records.html", {
        "sales": sales,
        "total_sales": total_sales,
        "cash_sales": cash_sales,
        "transfer_sales": transfer_sales,
        "pos_sales": pos_sales,
    })

@permission_required("inventory.view_sale", raise_exception=True)
def sale_detail(request, sale_id):

    sale = get_object_or_404(
        Sale.objects.select_related("processed_by").prefetch_related(
            "items__product"
        ),
        id=sale_id
    )

    system_settings = SystemSettings.load()

    return render(request, "sale_detail.html", {
        "sale": sale,
        "settings": system_settings,
    })
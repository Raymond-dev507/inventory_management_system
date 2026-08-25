import json
import time
import difflib

import requests

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from google import genai

from .store_insights import get_daily_store_data, get_period_sales_summary


# ==========================================================
# GEMINI CLIENT
# ==========================================================

client = genai.Client(
    api_key=settings.GEMINI_API_KEY
)


# ==========================================================
# TELEGRAM SEND MESSAGE
# ==========================================================
#
# Used by other parts of the application such as the
# daily AI report.
#
# The webhook itself does NOT use this function for normal
# replies. It returns Telegram's sendMessage method directly.
# ==========================================================

def send_telegram_message(message, chat_id=None):

    start = time.perf_counter()

    if chat_id is None:
        chat_id = settings.TELEGRAM_CHAT_ID

    url = (
        f"https://api.telegram.org/"
        f"bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
        },
        timeout=(3, 5),
    )

    elapsed = time.perf_counter() - start

    print("TELEGRAM SEND TIME:", round(elapsed, 3), "seconds")
    print("TELEGRAM STATUS:", response.status_code)

    return response


def edit_telegram_message(chat_id, message_id, text, reply_markup=None):
    """
    Edits an existing message — used to replace a
    did-you-mean suggestion (with buttons) with the final
    answer (without buttons) after the person taps one.
    """

    url = (
        f"https://api.telegram.org/"
        f"bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
    )

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    response = requests.post(url, json=payload, timeout=(3, 5))

    print("TELEGRAM EDIT STATUS:", response.status_code)

    return response


def answer_telegram_callback(callback_query_id, text=None, show_alert=False):
    """
    Acknowledges a button tap. Telegram shows a loading
    spinner on the button until this is called — without it,
    the spinner just sits there until it times out on its
    own, which feels broken even though the action already
    happened.
    """

    url = (
        f"https://api.telegram.org/"
        f"bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    )

    payload = {"callback_query_id": callback_query_id}

    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert

    response = requests.post(url, json=payload, timeout=(3, 5))

    print("TELEGRAM CALLBACK ACK STATUS:", response.status_code)

    return response


# ==========================================================
# TEXT NORMALIZATION
# ==========================================================

def normalize_text(value):
    """
    Normalize text so product/supplier matching is more
    reliable.
    """

    if value is None:
        return ""

    return " ".join(
        str(value)
        .strip()
        .lower()
        .split()
    )


# ==========================================================
# FIND PRODUCT
# ==========================================================

def find_product(products, name_hint):
    """
    Find a product using its exact name or SKU.

    We deliberately do NOT use loose partial matching such as:

        "rice" in "ricewater"

    because that can produce false matches.

    name_hint is typically the product_name extracted by the
    AI classifier, but can also be raw text.

    Returns:
        product dictionary
        or None
    """

    normalized_hint = normalize_text(name_hint)

    if not normalized_hint:
        return None

    hint_words = set(normalized_hint.split())

    # ------------------------------------------------------
    # FIRST: EXACT SKU / PRODUCT PHRASE
    # ------------------------------------------------------

    for product in products:

        product_name = normalize_text(product.get("name"))
        sku = normalize_text(product.get("sku"))

        if sku and sku in hint_words:
            return product

        if product_name:

            hint_padded = f" {normalized_hint} "
            name_padded = f" {product_name} "

            if name_padded in hint_padded:
                return product

    # ------------------------------------------------------
    # SECOND: SINGLE-WORD PRODUCT NAMES
    #
    # Example:
    #
    # Database: rice
    # Hint: "rice"
    #
    # This is safe because we compare complete words.
    # ------------------------------------------------------

    for product in products:

        product_name = normalize_text(product.get("name"))

        if not product_name:
            continue

        product_words = product_name.split()

        if len(product_words) == 1 and product_words[0] in hint_words:
            return product

    return None


# ==========================================================
# FIND SUPPLIER
# ==========================================================

def find_supplier(suppliers, name_hint):
    """
    Find a supplier only when the database name can be
    confidently matched.

    We do NOT return the first supplier when no match exists.
    """

    normalized_hint = normalize_text(name_hint)

    if not normalized_hint:
        return None

    hint_words = set(normalized_hint.split())

    # ------------------------------------------------------
    # EXACT FULL SUPPLIER NAME
    # ------------------------------------------------------

    for supplier in suppliers:

        supplier_name = normalize_text(supplier.get("name"))

        if not supplier_name:
            continue

        hint_padded = f" {normalized_hint} "
        name_padded = f" {supplier_name} "

        if name_padded in hint_padded:
            return supplier

    # ------------------------------------------------------
    # SINGLE WORD SUPPLIER NAME
    #
    # Example:
    #
    # Database: "jide"
    # Hint: "jide"
    # ------------------------------------------------------

    for supplier in suppliers:

        supplier_name = normalize_text(supplier.get("name"))

        if not supplier_name:
            continue

        supplier_words = supplier_name.split()

        if len(supplier_words) == 1 and supplier_words[0] in hint_words:
            return supplier

    return None


# ==========================================================
# DID-YOU-MEAN SUGGESTIONS
# ==========================================================
#
# Used only when find_product/find_supplier come back empty.
# Suggests the closest real name in the database using plain
# string similarity — no AI call needed, this is instant and
# free. If nothing is close enough (cutoff=0.6), returns None
# and the caller falls back to the plain "not found" message.
# ==========================================================

def suggest_product_name(products, hint):

    normalized_hint = normalize_text(hint)

    if not normalized_hint:
        return None

    name_lookup = {
        normalize_text(product.get("name")): product.get("name")
        for product in products
        if product.get("name")
    }

    matches = difflib.get_close_matches(
        normalized_hint,
        name_lookup.keys(),
        n=1,
        cutoff=0.6,
    )

    if not matches:
        return None

    return name_lookup[matches[0]]


def suggest_supplier_name(suppliers, hint):

    normalized_hint = normalize_text(hint)

    if not normalized_hint:
        return None

    name_lookup = {
        normalize_text(supplier.get("name")): supplier.get("name")
        for supplier in suppliers
        if supplier.get("name")
    }

    matches = difflib.get_close_matches(
        normalized_hint,
        name_lookup.keys(),
        n=1,
        cutoff=0.6,
    )

    if not matches:
        return None

    return name_lookup[matches[0]]


# ==========================================================
# CONFIRMATION KEYBOARDS FOR DID-YOU-MEAN SUGGESTIONS
# ==========================================================
#
# When a product/supplier isn't found but a close match
# exists, we show real Yes/No buttons instead of asking the
# person to type a confirmation — typed "yes" is ambiguous
# (it could mean anything), a button tap isn't.
#
# callback_data carries everything needed to answer once
# tapped, so we don't need to remember what was pending
# anywhere — it's self-contained in the button itself.
# Telegram limits callback_data to 64 bytes, so it's kept
# short: "p:INTENT:name" or "s:INTENT:name".
# ==========================================================

def build_suggestion_keyboard(kind, intent, suggested_name):

    callback_data = f"{kind}:{intent}:{suggested_name}"

    if len(callback_data.encode("utf-8")) > 64:
        callback_data = callback_data.encode("utf-8")[:64].decode(
            "utf-8", errors="ignore"
        )

    return {
        "inline_keyboard": [
            [
                {
                    "text": f"✅ Yes, {suggested_name}",
                    "callback_data": callback_data,
                },
                {
                    "text": "❌ No",
                    "callback_data": "no",
                },
            ]
        ]
    }


# ==========================================================
# INTENT CLASSIFICATION
# ==========================================================
#
# This replaces every keyword-list function that used to
# live here (is_product_question, is_supplier_question,
# is_total_inventory_question, is_all_supplier_question,
# get_period_sales_answer's period-detection, etc).
#
# Gemini is used ONLY to understand what the user means.
# It never generates the actual answer for these intents —
# the real numbers always come straight from the database.
# ==========================================================

INTENT_LIST = [
    "PRODUCT_STOCK",
    "PRODUCT_PRICE",
    "PRODUCT_SUPPLIER",
    "PRODUCT_SKU",
    "PRODUCT_GENERAL",
    "SUPPLIER_PRODUCTS",
    "SUPPLIER_CONTACT",
    "SUPPLIER_GENERAL",
    "ALL_SUPPLIERS",
    "TOTAL_INVENTORY",
    "RESTOCK_NEEDED",
    "OUT_OF_STOCK",
    "LOW_STOCK",
    "TOP_SELLING",
    "SALES_SUMMARY",
    "REVENUE",
    "PROFIT",
    "UNITS_SOLD",
    "TRANSACTIONS",
    "WHO_LOGGED_IN",
    "WHO_SOLD",
    "STOCK_IN_ACTIVITY",
    "STOCK_OUT_ACTIVITY",
    "GREETING_OR_SMALLTALK",
    "UNKNOWN",
]

PERIOD_LIST = ["today", "yesterday", "week", "month", "year", None]


def classify_question(question, context=None):
    """
    Uses Gemini purely to understand INTENT, never to
    generate facts.

    context is an optional dict:
        {"last_product_name": "rice", "last_supplier_name": None}

    passed in so Gemini can resolve follow-up questions like
    "what's the price?" or "who supplies it?" that don't
    repeat the product/supplier name, using whatever was
    last discussed in this chat.

    Returns a dict like:

    {
        "intent": "PRODUCT_STOCK",
        "product_names": ["rice"],
        "supplier_names": [],
        "period": None
    }

    product_names/supplier_names are always lists now (can
    be empty, or contain more than one name for questions
    like "how many rice and beans do we have").

    If classification fails for any reason, returns a safe
    UNKNOWN result instead of raising, so the webhook can
    fall back to the free-text Gemini answer.
    """

    context = context or {}
    last_product = context.get("last_product_name")
    last_supplier = context.get("last_supplier_name")

    context_block = ""

    if last_product or last_supplier:
        context_block = f"""
CONVERSATION CONTEXT (from earlier in this chat):
- Last product discussed: {last_product or "none"}
- Last supplier discussed: {last_supplier or "none"}

If the user's message clearly continues talking about that
same product/supplier without naming it again (e.g. "what's
the price?", "who supplies it?", "and the sku?"), resolve it
using the context above and put that name in product_names
or supplier_names. If the message names something different,
ignore the context and use what they actually said.
"""

    prompt = f"""
Classify the user's message for a Nigerian store inventory bot.
{context_block}
Return ONLY valid JSON, no explanation, matching this exact shape:

{{
  "intent": one of {INTENT_LIST},
  "product_names": a list of specific products mentioned (empty list if none),
  "supplier_names": a list of specific suppliers mentioned (empty list if none),
  "period": one of {PERIOD_LIST}
}}

Rules:
- product_names/supplier_names should be the raw name(s) as
  the user typed them (don't correct spelling), UNLESS
  resolved from conversation context as described above.
- A question can mention more than one product or supplier,
  e.g. "how many rice and beans do we have" ->
  product_names: ["rice", "beans"].
- period applies to sales/revenue/profit/units
  sold/transactions questions AND activity questions (who
  logged in, who sold, stock in/out) — e.g. "who sold rice
  yesterday" has period "yesterday". Default to null if no
  period is mentioned (callers treat null as "today").
- If the message is a greeting or small talk, use
  GREETING_OR_SMALLTALK.
- Use WHO_LOGGED_IN for questions about who logged into the
  system (e.g. "who logged in today", "who accessed the
  system this week").
- Use WHO_SOLD for questions about who sold something, or
  who made sales (e.g. "who sold rice today", "who made
  sales this month"). If specific products are mentioned,
  put them in product_names.
- Use STOCK_IN_ACTIVITY for questions about who added or
  brought in stock (e.g. "who restocked today", "who added
  inventory this week").
- Use STOCK_OUT_ACTIVITY for questions about who removed or
  took out stock, separate from a normal sale (e.g. "who
  removed stock yesterday").
- If you cannot confidently classify it, use UNKNOWN.

USER MESSAGE:
{question}
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
            },
        )

        parsed = json.loads(response.text)

        return {
            "intent": parsed.get("intent") or "UNKNOWN",
            "product_names": parsed.get("product_names") or [],
            "supplier_names": parsed.get("supplier_names") or [],
            "period": parsed.get("period"),
        }

    except Exception as e:

        print("INTENT CLASSIFICATION FAILED:", str(e))

        return {
            "intent": "UNKNOWN",
            "product_names": [],
            "supplier_names": [],
            "period": None,
        }


# ==========================================================
# CONVERSATION CONTEXT (FOLLOW-UP MEMORY)
# ==========================================================

def get_conversation_context(chat_id):
    """
    Loads (or creates) the small memory record for this
    chat, returned as a plain dict ready to hand to
    classify_question().
    """

    from .models import ConversationContext

    context_obj, _ = ConversationContext.objects.get_or_create(
        telegram_chat_id=chat_id
    )

    return {
        "last_product_name": context_obj.last_product_name,
        "last_supplier_name": context_obj.last_supplier_name,
    }


def update_conversation_context(chat_id, product_name=None, supplier_name=None):
    """
    Updates whichever of product/supplier was actually
    resolved this turn. Only overwrites a field if a new
    value is given — asking about a supplier shouldn't erase
    the last product discussed, since a later "what's its
    price?" might still mean the product.
    """

    if not product_name and not supplier_name:
        return

    from .models import ConversationContext

    context_obj, _ = ConversationContext.objects.get_or_create(
        telegram_chat_id=chat_id
    )

    if product_name:
        context_obj.last_product_name = product_name

    if supplier_name:
        context_obj.last_supplier_name = supplier_name

    context_obj.save()


# ==========================================================
# BUILD TOTAL INVENTORY ANSWER
# ==========================================================

def get_total_inventory_answer(store_data):

    products = store_data.get("products", [])

    if not products:
        return "📦 There are currently no products in the inventory."

    total_quantity = sum(
        int(product.get("quantity", 0) or 0)
        for product in products
    )

    product_lines = [
        f"• {product.get('name', 'Unknown')} "
        f"({int(product.get('quantity', 0) or 0)} units)"
        for product in products
    ]

    return (
        f"📦 Total inventory quantity: {total_quantity} units.\n"
        f"📊 Products counted: {len(products)}\n\n"
        f"🗂️ Products:\n"
        + "\n".join(product_lines)
    )


# ==========================================================
# BUILD ALL-SUPPLIERS ANSWER
# ==========================================================

def get_all_suppliers_answer(suppliers):

    if not suppliers:
        return "📊 No suppliers were found in the store database."

    lines = []

    for supplier in suppliers:

        products = supplier.get("products", [])

        lines.append(
            f"🏢 {supplier.get('name', 'Unknown')} "
            f"— {len(products)} product(s)"
        )

    return "🏢 Your suppliers:\n\n" + "\n".join(lines)


# ==========================================================
# BUILD SUPPLIER ANSWER
# ==========================================================

def get_supplier_answer(intent, supplier):
    """
    Handle supplier questions using the classified intent
    rather than re-scanning raw text.
    """

    supplier_name = supplier.get("name", "Unknown supplier")
    products = supplier.get("products", [])

    if intent == "SUPPLIER_PRODUCTS":

        if not products:
            return (
                f"🏢 {supplier_name} currently has "
                f"no products linked to them."
            )

        return (
            f"🏢 Supplier: {supplier_name}\n\n"
            f"📦 Products supplied:\n"
            + "\n".join(f"• {product}" for product in products)
        )

    if intent == "SUPPLIER_CONTACT":

        return (
            f"🏢 {supplier_name}\n"
            f"📞 Phone: {supplier.get('phone') or 'Not provided'}\n"
            f"📧 Email: {supplier.get('email') or 'Not provided'}\n"
            f"📍 Address: {supplier.get('address') or 'Not provided'}"
        )

    # SUPPLIER_GENERAL / fallback

    product_text = ", ".join(products) if products else "None"

    return (
        f"🏢 Supplier: {supplier_name}\n"
        f"📞 Phone: {supplier.get('phone') or 'Not provided'}\n"
        f"📧 Email: {supplier.get('email') or 'Not provided'}\n"
        f"📍 Address: {supplier.get('address') or 'Not provided'}\n"
        f"📦 Products: {product_text}"
    )


# ==========================================================
# BUILD PRODUCT ANSWER
# ==========================================================

def get_product_answer(intent, product):
    """
    Handle product-specific questions using the classified
    intent rather than re-scanning raw text.
    """

    product_name = product.get("name", "Unknown product")
    sku = product.get("sku", "Not provided")
    category = product.get("category", "Not provided")
    supplier = product.get("supplier", "Not provided")
    quantity = int(product.get("quantity", 0) or 0)
    cost_price = float(product.get("cost_price", 0) or 0)
    selling_price = float(product.get("selling_price", 0) or 0)

    if intent == "PRODUCT_STOCK":
        return (
            f"📦 {product_name}\n"
            f"📊 Current stock: {quantity} units"
        )

    if intent == "PRODUCT_PRICE":
        return (
            f"📦 {product_name}\n"
            f"💰 Cost price: ₦{cost_price:,.2f}\n"
            f"🏷️ Selling price: ₦{selling_price:,.2f}"
        )

    if intent == "PRODUCT_SUPPLIER":
        return f"📦 {product_name}\n🏢 Supplier: {supplier}"

    if intent == "PRODUCT_SKU":
        return f"📦 {product_name}\n🏷️ SKU: {sku}"

    # PRODUCT_GENERAL / fallback

    return (
        f"📦 Product: {product_name}\n"
        f"🏷️ SKU: {sku}\n"
        f"📂 Category: {category}\n"
        f"🏢 Supplier: {supplier}\n"
        f"📊 Stock: {quantity} units\n"
        f"💰 Cost price: ₦{cost_price:,.2f}\n"
        f"🏷️ Selling price: ₦{selling_price:,.2f}"
    )


# ==========================================================
# OUT OF STOCK / LOW STOCK / RESTOCK / TOP SELLING ANSWERS
# ==========================================================

def get_out_of_stock_answer(store_data):

    out_of_stock = store_data.get("out_of_stock_products", [])

    if not out_of_stock:
        return "✅ There are currently no out-of-stock products."

    lines = [
        f"🔴 {product['name']} — {product['quantity']} units"
        for product in out_of_stock
    ]

    return "🚨 Out-of-stock products:\n\n" + "\n".join(lines)


def get_low_stock_answer(store_data):

    low_stock = store_data.get("low_stock_products", [])

    if not low_stock:
        return "✅ There are currently no low-stock products."

    lines = [
        f"⚠️ {product['name']} — {product['quantity']} units"
        for product in low_stock
    ]

    return "⚠️ Low-stock products:\n\n" + "\n".join(lines)


def get_restock_answer(store_data):

    out_of_stock = store_data.get("out_of_stock_products", [])
    low_stock = store_data.get("low_stock_products", [])
    products_to_restock = out_of_stock + low_stock

    if not products_to_restock:
        return "✅ No products currently need restocking."

    lines = []

    for product in products_to_restock:

        name = product.get("name", "Unknown product")
        quantity = int(product.get("quantity", 0) or 0)

        if quantity <= 0:
            lines.append(f"🔴 {name} — OUT OF STOCK")
        else:
            lines.append(f"⚠️ {name} — {quantity} units left")

    return "🛒 Products that need restocking:\n\n" + "\n".join(lines)


def get_top_selling_answer(store_data):

    best_selling = store_data.get("best_selling_products", [])

    if not best_selling:
        return "📊 No products have been sold today."

    top_product = best_selling[0]

    return (
        f"🏆 Top-selling product today: {top_product['name']} "
        f"with {top_product['units_sold']} units sold."
    )


# ==========================================================
# TIMESTAMP FORMATTING
# ==========================================================

def format_time(iso_timestamp):
    """
    Converts a raw ISO timestamp (e.g.
    "2026-08-18T11:44:43.550288+00:00") into a clean,
    human-readable time (e.g. "11:44 AM") for Telegram.

    Falls back to the raw string if parsing fails, rather
    than raising.
    """

    if not iso_timestamp:
        return "Unknown time"

    try:
        from datetime import datetime

        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%I:%M %p").lstrip("0")

    except Exception:
        return iso_timestamp


# ==========================================================
# PERIOD NAMES (shared by sales AND activity answers)
# ==========================================================

PERIOD_NAMES = {
    "today": "today",
    "yesterday": "yesterday",
    "week": "this week",
    "month": "this month",
    "year": "this year",
}


def _get_activity_data_for_period(store_data, period):
    """
    "today" reuses the store_data already fetched for this
    request (no extra query). Any other period fetches fresh
    from the database via get_activity_period_summary().

    Returns None if the period string isn't recognized.
    """

    period = period or "today"

    if period not in PERIOD_NAMES:
        return None, None

    period_name = PERIOD_NAMES[period]

    if period == "today":
        return store_data, period_name

    from .store_insights import get_activity_period_summary

    activity_data = get_activity_period_summary(period)

    return activity_data, period_name


# ==========================================================
# ACTIVITY ANSWERS — WHO LOGGED IN / SOLD / STOCKED
# ==========================================================

def get_who_logged_in_answer(store_data, period=None):

    activity_data, period_name = _get_activity_data_for_period(store_data, period)

    if activity_data is None:
        return (
            "❌ I couldn't understand that period — try today, "
            "yesterday, this week, this month, or this year."
        )

    logins = activity_data.get("login_activities", [])

    if not logins:
        return f"🔑 No one logged in {period_name}."

    lines = [
        f"🔑 {activity.get('user', 'Unknown')} — "
        f"{format_time(activity.get('timestamp'))}"
        for activity in logins
    ]

    return f"🔑 Logins for {period_name}:\n\n" + "\n".join(lines)


def get_who_sold_answer(store_data, product_names=None, period=None):
    """
    Shows who sold what in the given period. If
    product_names is given, filters to sales of those
    specific products only.
    """

    activity_data, period_name = _get_activity_data_for_period(store_data, period)

    if activity_data is None:
        return (
            "❌ I couldn't understand that period — try today, "
            "yesterday, this week, this month, or this year."
        )

    sales = activity_data.get("sales_activity", [])

    if not sales:
        return f"🧾 No sales have been recorded {period_name}."

    product_names = [name for name in (product_names or []) if name]

    if product_names:

        normalized_targets = {
            normalize_text(name) for name in product_names
        }

        sales = [
            sale for sale in sales
            if normalize_text(sale.get("product", "")) in normalized_targets
        ]

        if not sales:
            return (
                f"🧾 No sales of "
                f"{', '.join(product_names)} {period_name}."
            )

    lines = [
        f"🧾 {sale.get('user', 'Unknown')} sold "
        f"{sale.get('quantity', 0)} x {sale.get('product', 'Unknown')} "
        f"(₦{sale.get('subtotal', 0):,.2f})"
        for sale in sales
    ]

    return f"🧾 Sales activity for {period_name}:\n\n" + "\n".join(lines)


def get_stock_in_answer(store_data, period=None):

    activity_data, period_name = _get_activity_data_for_period(store_data, period)

    if activity_data is None:
        return (
            "❌ I couldn't understand that period — try today, "
            "yesterday, this week, this month, or this year."
        )

    activities = activity_data.get("stock_in_activities", [])

    if not activities:
        return f"📥 No stock was added {period_name}."

    lines = [
        f"📥 {activity.get('user', 'Unknown')} — "
        f"{activity.get('description', 'No details')} "
        f"({format_time(activity.get('timestamp'))})"
        for activity in activities
    ]

    return f"📥 Stock added {period_name}:\n\n" + "\n".join(lines)


def get_stock_out_answer(store_data, period=None):

    activity_data, period_name = _get_activity_data_for_period(store_data, period)

    if activity_data is None:
        return (
            "❌ I couldn't understand that period — try today, "
            "yesterday, this week, this month, or this year."
        )

    activities = activity_data.get("stock_out_activities", [])

    if not activities:
        return f"📤 No stock was removed {period_name}."

    lines = [
        f"📤 {activity.get('user', 'Unknown')} — "
        f"{activity.get('description', 'No details')} "
        f"({format_time(activity.get('timestamp'))})"
        for activity in activities
    ]

    return f"📤 Stock removed {period_name}:\n\n" + "\n".join(lines)


# ==========================================================
# SALES / REVENUE / PROFIT ANSWER (WITH PERIOD)
# ==========================================================

def get_sales_intent_answer(intent, period):
    """
    Handles REVENUE, PROFIT, UNITS_SOLD, TRANSACTIONS,
    SALES_SUMMARY for any period. Falls back to "today" data
    already computed in store_data isn't needed here — we
    always pull fresh period data from the database so any
    period works consistently.
    """

    if period not in PERIOD_NAMES:
        period = "today"

    period_name = PERIOD_NAMES[period]

    summary = get_period_sales_summary(period)

    if summary is None:
        return (
            "❌ I couldn't calculate that — please try "
            "asking about today, yesterday, this week, "
            "this month, or this year."
        )

    if intent == "REVENUE":
        return f"💰 Revenue for {period_name}: ₦{summary['revenue']:,.2f}"

    if intent == "PROFIT":
        return f"📈 Profit for {period_name}: ₦{summary['profit']:,.2f}"

    if intent == "UNITS_SOLD":
        return f"📦 Units sold for {period_name}: {summary['units_sold']}"

    if intent == "TRANSACTIONS":
        return f"🧾 Transactions for {period_name}: {summary['transactions']}"

    # SALES_SUMMARY / fallback

    return (
        f"📊 Sales summary for {period_name}:\n\n"
        f"💰 Revenue: ₦{summary['revenue']:,.2f}\n"
        f"📈 Profit: ₦{summary['profit']:,.2f}\n"
        f"📦 Units sold: {summary['units_sold']}\n"
        f"🧾 Transactions: {summary['transactions']}"
    )


# ==========================================================
# INTENT-BASED ROUTING
# ==========================================================
#
# This replaces get_fast_database_answer(). It classifies
# the question once, then routes to the correct deterministic
# database function. If the intent is UNKNOWN, it returns
# None so the webhook falls back to the free-text Gemini
# answer instead of printing an error.
# ==========================================================

def get_answer_from_intent(question, store_data, chat_id):

    context = get_conversation_context(chat_id)
    classification = classify_question(question, context)
    intent = classification["intent"]

    products = store_data.get("products", [])
    suppliers = store_data.get("suppliers", [])

    print("INTENT:", intent, "| DATA:", classification)

    # ------------------------------------------------------
    # GREETING
    # ------------------------------------------------------

    if intent == "GREETING_OR_SMALLTALK":
        return (
            "👋 Hi! Ask me about stock levels, prices, "
            "suppliers, sales, or what needs restocking."
        )

    # ------------------------------------------------------
    # PRODUCT INTENTS
    #
    # Loops over every product mentioned, so "how many rice
    # and beans do we have" answers both instead of just the
    # first one. If Gemini didn't extract any names at all,
    # falls back to the raw question as a single hint (same
    # behavior as before this change).
    # ------------------------------------------------------

    if intent in (
        "PRODUCT_STOCK",
        "PRODUCT_PRICE",
        "PRODUCT_SUPPLIER",
        "PRODUCT_SKU",
        "PRODUCT_GENERAL",
    ):

        targets = classification["product_names"] or [question]

        # ---- single item + not found + suggestion exists:
        # show real Yes/No buttons instead of plain text ----

        if len(targets) == 1:

            target = targets[0]
            product = find_product(products, target)

            if product is not None:

                update_conversation_context(
                    chat_id,
                    product_name=product.get("name"),
                )

                return get_product_answer(intent, product)

            suggestion = suggest_product_name(products, target)

            if suggestion:

                return {
                    "text": (
                        f"❌ I couldn't find '{target}'. "
                        f"Did you mean '{suggestion}'?"
                    ),
                    "reply_markup": build_suggestion_keyboard(
                        "p", intent, suggestion
                    ),
                }

            return (
                f"❌ I couldn't find '{target}' in the "
                f"store database."
            )

        # ---- multiple items: loop and answer each in plain
        # text (buttons don't make sense for several at once) ----

        answer_blocks = []
        last_matched_product = None

        for target in targets:

            product = find_product(products, target)

            if product is not None:

                answer_blocks.append(get_product_answer(intent, product))
                last_matched_product = product.get("name")
                continue

            suggestion = suggest_product_name(products, target)

            if suggestion:
                answer_blocks.append(
                    f"❌ I couldn't find '{target}'. "
                    f"Did you mean '{suggestion}'?"
                )
            else:
                answer_blocks.append(
                    f"❌ I couldn't find '{target}' in the "
                    f"store database."
                )

        update_conversation_context(
            chat_id,
            product_name=last_matched_product,
        )

        return "\n\n".join(answer_blocks)

    # ------------------------------------------------------
    # SUPPLIER INTENTS
    # ------------------------------------------------------

    if intent == "ALL_SUPPLIERS":
        return get_all_suppliers_answer(suppliers)

    if intent in ("SUPPLIER_PRODUCTS", "SUPPLIER_CONTACT", "SUPPLIER_GENERAL"):

        targets = classification["supplier_names"] or [question]

        if len(targets) == 1:

            target = targets[0]
            supplier = find_supplier(suppliers, target)

            if supplier is not None:

                update_conversation_context(
                    chat_id,
                    supplier_name=supplier.get("name"),
                )

                return get_supplier_answer(intent, supplier)

            suggestion = suggest_supplier_name(suppliers, target)

            if suggestion:

                return {
                    "text": (
                        f"❌ I couldn't find '{target}'. "
                        f"Did you mean '{suggestion}'?"
                    ),
                    "reply_markup": build_suggestion_keyboard(
                        "s", intent, suggestion
                    ),
                }

            return (
                f"❌ I couldn't find '{target}' in the "
                f"store database."
            )

        answer_blocks = []
        last_matched_supplier = None

        for target in targets:

            supplier = find_supplier(suppliers, target)

            if supplier is not None:

                answer_blocks.append(get_supplier_answer(intent, supplier))
                last_matched_supplier = supplier.get("name")
                continue

            suggestion = suggest_supplier_name(suppliers, target)

            if suggestion:
                answer_blocks.append(
                    f"❌ I couldn't find '{target}'. "
                    f"Did you mean '{suggestion}'?"
                )
            else:
                answer_blocks.append(
                    f"❌ I couldn't find '{target}' in the "
                    f"store database."
                )

        update_conversation_context(
            chat_id,
            supplier_name=last_matched_supplier,
        )

        return "\n\n".join(answer_blocks)

    # ------------------------------------------------------
    # INVENTORY-WIDE INTENTS
    # ------------------------------------------------------

    if intent == "TOTAL_INVENTORY":
        return get_total_inventory_answer(store_data)

    if intent == "RESTOCK_NEEDED":
        return get_restock_answer(store_data)

    if intent == "OUT_OF_STOCK":
        return get_out_of_stock_answer(store_data)

    if intent == "LOW_STOCK":
        return get_low_stock_answer(store_data)

    if intent == "TOP_SELLING":
        return get_top_selling_answer(store_data)

    # ------------------------------------------------------
    # SALES INTENTS (WITH PERIOD)
    # ------------------------------------------------------

    if intent in ("SALES_SUMMARY", "REVENUE", "PROFIT", "UNITS_SOLD", "TRANSACTIONS"):
        period = classification["period"] or "today"
        return get_sales_intent_answer(intent, period)

    # ------------------------------------------------------
    # ACTIVITY INTENTS — now work for any period, not just
    # today, using the same period value the classifier
    # already extracts for sales questions.
    # ------------------------------------------------------

    if intent == "WHO_LOGGED_IN":
        return get_who_logged_in_answer(
            store_data,
            classification["period"],
        )

    if intent == "WHO_SOLD":
        return get_who_sold_answer(
            store_data,
            classification["product_names"],
            classification["period"],
        )

    if intent == "STOCK_IN_ACTIVITY":
        return get_stock_in_answer(
            store_data,
            classification["period"],
        )

    if intent == "STOCK_OUT_ACTIVITY":
        return get_stock_out_answer(
            store_data,
            classification["period"],
        )

    # ------------------------------------------------------
    # UNKNOWN — let the webhook fall through to Gemini
    # free-text answer instead of printing an error.
    # ------------------------------------------------------

    return None


# ==========================================================
# GEMINI FREE-TEXT FALLBACK
# ==========================================================
#
# Only reached when classify_question() itself returns
# UNKNOWN (or classification failed). It must never invent
# database information — it only reasons over the store data
# it's handed.
# ==========================================================

def get_gemini_answer(question, store_data):

    prompt = f"""
You are an AI business assistant for an inventory management system in Nigeria.

Answer the user's question using ONLY the store data provided below.

STRICT RULES:

- Do not invent information.
- Do not invent products.
- Do not invent suppliers.
- Do not invent stock.
- Do not invent quantities.
- Do not invent sales.
- Do not invent revenue.
- Do not invent profit.
- Do not invent staff activity.
- Do not invent prices.
- Do not invent SKU numbers.
- Do not assume information that is not present.
- All money is Nigerian Naira (₦).
- Never use USD or $.
- If the store data does not contain the information,
  clearly say that the information is not available.
- Keep the answer concise.
- Answer the user's question directly.
- Do not claim technical problems without evidence.
- Do not use outside knowledge to answer store-data
  questions.

STORE DATA:

{store_data}

USER QUESTION:

{question}

Give the best answer based ONLY on the store data.
"""

    start = time.perf_counter()

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
        )

        answer = (
            response.text
            or "I could not generate an answer from the available store data."
        )

    except Exception as e:

        print("GEMINI FALLBACK FAILED:", str(e))

        answer = (
            "⚠️ I couldn't process that question right now. "
            "Please try rephrasing it, or ask about a "
            "specific product, supplier, or sales figure."
        )

    elapsed = time.perf_counter() - start

    print("GEMINI API TIME:", round(elapsed, 3), "seconds")

    # Remove Markdown headings that could cause
    # unnecessary formatting in Telegram.

    answer = answer.replace("#", "").strip()

    return answer


# ==========================================================
# ACCESS CONTROL
# ==========================================================
#
# Only chat_ids that exist in AuthorizedTelegramUser (and
# are marked active) may use the bot. Everyone else gets a
# safe generic message pointing them to /myid — never store
# data.
# ==========================================================

def get_authorized_user(chat_id):
    """
    Returns the AuthorizedTelegramUser for this chat_id,
    or None if they are not authorized.

    Only superusers are ever granted access — even if a
    row exists in AuthorizedTelegramUser for a non-superuser
    account, this returns None for them. This keeps the bot
    strictly owner-only.
    """

    from .models import AuthorizedTelegramUser

    try:
        authorized_user = (
            AuthorizedTelegramUser.objects
            .select_related("linked_user")
            .get(
                telegram_chat_id=chat_id,
                is_active=True,
            )
        )
    except AuthorizedTelegramUser.DoesNotExist:
        return None

    if not authorized_user.linked_user.is_superuser:
        return None

    return authorized_user


# ==========================================================
# BUTTON TAP HANDLER (callback_query updates)
# ==========================================================
#
# A tapped inline button arrives as an entirely different
# update shape from a typed message — Telegram sends
# "callback_query", not "message". This resolves the tap
# using only what's encoded in callback_data, so it works
# correctly even if the person asks something unrelated
# before tapping the button.
# ==========================================================

def handle_callback_query(callback_query):

    callback_id = callback_query.get("id")
    message = callback_query.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    data_str = callback_query.get("data", "")

    if not chat_id or not callback_id:
        return

    # ------------------------------------------------------
    # SAME ACCESS CONTROL AS EVERYTHING ELSE
    # ------------------------------------------------------

    authorized_user = get_authorized_user(chat_id)

    if authorized_user is None:

        answer_telegram_callback(
            callback_id,
            "This bot is private and only works for the store owner.",
            show_alert=True,
        )

        return

    # ------------------------------------------------------
    # "NO" — DISMISS THE SUGGESTION
    # ------------------------------------------------------

    if data_str == "no":

        answer_telegram_callback(callback_id, "Okay.")

        edit_telegram_message(
            chat_id,
            message_id,
            "❌ Okay, never mind.",
        )

        return

    # ------------------------------------------------------
    # "YES" — RESOLVE THE CONFIRMED PRODUCT/SUPPLIER
    #
    # callback_data is "p:INTENT:name" or "s:INTENT:name",
    # entirely self-contained — no dependency on remembered
    # state, so this works correctly even minutes later.
    # ------------------------------------------------------

    try:
        kind, intent, name = data_str.split(":", 2)
    except ValueError:

        answer_telegram_callback(
            callback_id,
            "Something went wrong with that button.",
            show_alert=True,
        )

        return

    store_data = get_daily_store_data()

    if kind == "p":

        product = find_product(store_data.get("products", []), name)

        if product is None:
            answer_telegram_callback(
                callback_id,
                "That product no longer exists.",
                show_alert=True,
            )
            edit_telegram_message(
                chat_id,
                message_id,
                f"❌ '{name}' no longer exists in the store database.",
            )
            return

        answer_text = get_product_answer(intent, product)
        update_conversation_context(chat_id, product_name=product.get("name"))

    elif kind == "s":

        supplier = find_supplier(store_data.get("suppliers", []), name)

        if supplier is None:
            answer_telegram_callback(
                callback_id,
                "That supplier no longer exists.",
                show_alert=True,
            )
            edit_telegram_message(
                chat_id,
                message_id,
                f"❌ '{name}' no longer exists in the store database.",
            )
            return

        answer_text = get_supplier_answer(intent, supplier)
        update_conversation_context(chat_id, supplier_name=supplier.get("name"))

    else:

        answer_telegram_callback(
            callback_id,
            "Unrecognized button.",
            show_alert=True,
        )

        return

    answer_telegram_callback(callback_id)
    edit_telegram_message(chat_id, message_id, answer_text)


# ==========================================================
# TELEGRAM WEBHOOK
# ==========================================================

@csrf_exempt
def telegram_webhook(request):

    request_start = time.perf_counter()

    # ======================================================
    # ONLY POST
    # ======================================================

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error": "Only POST requests are allowed",
            },
            status=405,
        )

    try:

        # ==================================================
        # RECEIVE TELEGRAM UPDATE
        # ==================================================

        data = json.loads(request.body)

        print("TELEGRAM WEBHOOK DATA:")
        print(data)

        # ==================================================
        # BUTTON TAP (callback_query) — different update
        # shape from a typed message, handled separately.
        # ==================================================

        callback_query = data.get("callback_query")

        if callback_query:

            handle_callback_query(callback_query)

            return JsonResponse({"ok": True})

        # ==================================================
        # GET MESSAGE
        # ==================================================

        message = data.get("message")

        if not message:
            return JsonResponse({"ok": True})

        text = message.get("text", "").strip()

        if not text:
            return JsonResponse({"ok": True})

        # ==================================================
        # CHAT ID
        # ==================================================

        chat = message.get("chat", {})
        chat_id = chat.get("id")

        if not chat_id:
            return JsonResponse({"ok": True})

        print("USER QUESTION:", text)

        # ==================================================
        # /MYID — always allowed, returns no store data
        # ==================================================

        if normalize_text(text) == "/myid":

            username = message.get("from", {}).get("username", "unknown")

            return JsonResponse(
                {
                    "method": "sendMessage",
                    "chat_id": chat_id,
                    "text": (
                        f"Your Telegram chat ID is:\n\n"
                        f"{chat_id}\n\n"
                        f"Username: @{username}\n\n"
                        f"Send this to the store owner to "
                        f"get access."
                    ),
                }
            )

        # ==================================================
        # ACCESS CONTROL — everything below this line
        # requires authorization
        # ==================================================

        authorized_user = get_authorized_user(chat_id)

        if authorized_user is None:

            print("UNAUTHORIZED ACCESS ATTEMPT:", chat_id)

            return JsonResponse(
                {
                    "method": "sendMessage",
                    "chat_id": chat_id,
                    "text": (
                        "🚫 This bot is private and only "
                        "works for the store owner."
                    ),
                }
            )

        # ==================================================
        # /REPORT
        # ==================================================

        if normalize_text(text) == "/report":

            print("REPORT COMMAND RECEIVED")

            from .ai_report import generate_report

            generate_report(chat_id=chat_id)

            print("DAILY REPORT SENT")

            return JsonResponse(
                {
                    "ok": True,
                    "source": "daily_report",
                }
            )

        # ==================================================
        # GET STORE DATA
        # ==================================================

        store_start = time.perf_counter()
        store_data = get_daily_store_data()
        store_time = time.perf_counter() - store_start

        print("STORE DATA TIME:", round(store_time, 3), "seconds")

        # ==================================================
        # AI INTENT ROUTING
        # ==================================================

        answer = get_answer_from_intent(text, store_data, chat_id)

        # ==================================================
        # DETERMINISTIC ANSWER FOUND
        # ==================================================

        if answer:

            print("ANSWER TYPE: INTENT-ROUTED DATABASE ANSWER")
            print("ANSWER:")
            print(answer)

            total_time = time.perf_counter() - request_start
            print("TOTAL REQUEST TIME:", round(total_time, 3), "seconds")

            # ----------------------------------------------
            # answer is either a plain string, or a dict
            # {"text": ..., "reply_markup": ...} when a
            # did-you-mean suggestion needs Yes/No buttons.
            # ----------------------------------------------

            if isinstance(answer, dict):

                response_body = {
                    "method": "sendMessage",
                    "chat_id": chat_id,
                    "text": answer["text"],
                }

                if answer.get("reply_markup"):
                    response_body["reply_markup"] = answer["reply_markup"]

                return JsonResponse(response_body)

            return JsonResponse(
                {
                    "method": "sendMessage",
                    "chat_id": chat_id,
                    "text": answer,
                }
            )

        # ==================================================
        # GEMINI FREE-TEXT FALLBACK (intent was UNKNOWN)
        #
        # Only the owner (superuser) ever reaches this point
        # at all — get_authorized_user() already blocked
        # everyone else earlier in this function.
        # ==================================================

        print("ANSWER TYPE: GEMINI FREE-TEXT")

        ai_answer = get_gemini_answer(text, store_data)

        print("GEMINI ANSWER:")
        print(ai_answer)

        total_time = time.perf_counter() - request_start
        print("TOTAL REQUEST TIME:", round(total_time, 3), "seconds")

        return JsonResponse(
            {
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": ai_answer,
            }
        )

    # ======================================================
    # INVALID JSON
    # ======================================================

    except json.JSONDecodeError:

        print("WEBHOOK ERROR: Invalid JSON")

        return JsonResponse(
            {
                "ok": False,
                "error": "Invalid JSON",
            },
            status=400,
        )

    # ======================================================
    # GENERAL ERROR
    # ======================================================

    except Exception as e:

        print("WEBHOOK ERROR:", str(e))

        # --------------------------------------------------
        # Return HTTP 200.
        #
        # This prevents Telegram from repeatedly retrying
        # the same webhook update.
        # --------------------------------------------------

        return JsonResponse(
            {
                "ok": True,
                "error": "The request could not be processed.",
            }
        )
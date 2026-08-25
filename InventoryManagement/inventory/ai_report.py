
import requests

from django.http import JsonResponse
from django.conf import settings
from google import genai

from .Telegram import send_telegram_message
from .store_insights import get_daily_store_data


client = genai.Client(
    api_key=settings.GEMINI_API_KEY
)


def generate_report(chat_id=None):

    store_data = get_daily_store_data()

    store_owner = "Mr. Raymond"

    prompt = f"""
You are a business intelligence assistant for an inventory management system.

The store owner is: {store_owner}
The store is located in Nigeria.

IMPORTANT:

- All monetary values are Nigerian Naira (₦).
- Never use $, USD, or any other currency.
- Do not invent information.
- Do not guess the identity of the store owner.
- Never present 30-day sales as today's sales.
- If today's sales are zero, clearly say today's sales are zero.
- Slow-selling product figures are based on the last 30 days, not today.
- Do not assume the store has a technical problem just because there are no sales or logins.
- If there is no activity, state that no activity was recorded and recommend checking whether the store was open.
- Never claim a technical problem unless the store data provides evidence of one.
- Do not use # symbols.
_ make the message cleaner don't use # symbols. to start use something interesting.
- Use interesting and appropriate icons.
- Keep the report clear and useful.
- Do not invent recommendations based on information that is not in the store data.

Create a daily business report for the store owner.

STORE DATA:

{store_data}

Include:

1. Sales performance
2. Revenue
3. Profit
4. Units sold
5. Transactions
6. Who sold what
7. Staff login activity
8. Stock-in activity
9. Stock-out activity
10. Out-of-stock products
11. Low-stock products
12. Best-selling products TODAY
13. Slow-selling products over the LAST 30 DAYS
14. Important warnings
15. Practical recommendations

Start the report with:

📊 DAILY BUSINESS REPORT: {store_data["date"]}
To: {store_owner}

Format it clearly for Telegram.
"""

    # Generate report with Gemini

    response = client.interactions.create(
        model="gemini-3.1-flash-lite",
        input=prompt
    )

    ai_report = response.output_text

    # Remove accidental # symbols

    ai_report = ai_report.replace("#", "")

    # Send to requested chat

    if chat_id is not None:

        url = (
            f"https://api.telegram.org/"
            f"bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        telegram_response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": ai_report
            },
            timeout=10
        )

    else:

        telegram_response = send_telegram_message(
            ai_report
        )

    return ai_report, telegram_response


def generate_ai_report(request):

    ai_report, telegram_response = generate_report()

    return JsonResponse({
        "ai_report": ai_report,
        "telegram_status": telegram_response.status_code,
        "telegram_response": telegram_response.json(),
    })


def test_telegram(request):

    response = send_telegram_message(
        "🤖 Hello! Your Inventory Management Telegram bot is working."
    )

    return JsonResponse({
        "status": response.status_code,
        "response": response.json()
    })


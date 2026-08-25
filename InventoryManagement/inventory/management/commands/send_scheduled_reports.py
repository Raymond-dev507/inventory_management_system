from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import SystemSettings, AuthorizedTelegramUser
from ...ai_report import generate_report
from ...store_insights import get_daily_store_data
from ...Telegram import (
    send_telegram_message,
    get_out_of_stock_answer,
    get_low_stock_answer,
    get_top_selling_answer,
    get_sales_intent_answer,
)


# How many minutes past the scheduled time we still consider
# "due". This exists because the task runs periodically
# (e.g. every 10 minutes) rather than at the exact second —
# so if daily_report_time is 8:00 PM and this task runs at
# 8:00, 8:10, 8:20..., the 8:00 run needs a window to catch it.
#
# Keep this GREATER than your Task Scheduler's run interval,
# or a report could be skipped entirely if the exact minute
# is missed.

DUE_WINDOW_MINUTES = 15


class Command(BaseCommand):

    help = (
        "Checks daily_report_time and ai_report_time against "
        "the current time, and sends whichever report(s) are "
        "due and haven't already been sent today. Intended to "
        "be run frequently (e.g. every 10 minutes) via "
        "Task Scheduler / cron."
    )

    def handle(self, *args, **options):

        system_settings = SystemSettings.load()

        now = timezone.localtime()
        today = now.date()

        self.stdout.write(
            f"Checking scheduled reports at {now.strftime('%H:%M')}..."
        )

        # ----------------------------------------------------
        # PLAIN DAILY SUMMARY
        # ----------------------------------------------------

        if system_settings.daily_report_enabled:

            already_sent_today = (
                system_settings.last_daily_report_sent == today
            )

            if already_sent_today:

                self.stdout.write(
                    "Daily summary already sent today. Skipping."
                )

            elif self.is_due(now, system_settings.daily_report_time):

                self.send_plain_summary(system_settings, today)

            else:

                self.stdout.write(
                    f"Daily summary not due yet "
                    f"(scheduled {system_settings.daily_report_time})."
                )

        else:

            self.stdout.write(
                "Daily summary is disabled in Settings."
            )

        # ----------------------------------------------------
        # AI REPORT
        # ----------------------------------------------------

        if system_settings.ai_report_enabled:

            already_sent_today = (
                system_settings.last_ai_report_sent == today
            )

            if already_sent_today:

                self.stdout.write(
                    "AI report already sent today. Skipping."
                )

            elif self.is_due(now, system_settings.ai_report_time):

                self.send_ai_report(system_settings, today)

            else:

                self.stdout.write(
                    f"AI report not due yet "
                    f"(scheduled {system_settings.ai_report_time})."
                )

        else:

            self.stdout.write(
                "AI report is disabled in Settings."
            )

    # ==========================================================
    # TIME CHECK
    # ==========================================================

    def is_due(self, now, scheduled_time):
        """
        True if `now` is at or after `scheduled_time` today,
        but no more than DUE_WINDOW_MINUTES late.
        """

        scheduled_dt = now.replace(
            hour=scheduled_time.hour,
            minute=scheduled_time.minute,
            second=0,
            microsecond=0,
        )

        window_end = scheduled_dt + timedelta(minutes=DUE_WINDOW_MINUTES)

        return scheduled_dt <= now <= window_end

    # ==========================================================
    # PLAIN DAILY SUMMARY
    # ==========================================================

    def send_plain_summary(self, system_settings, today):

        self.stdout.write("Sending plain daily summary...")

        try:

            store_data = get_daily_store_data()

            sections = [
                "📋 DAILY STORE SUMMARY\n",
                get_sales_intent_answer("SALES_SUMMARY", "today"),
                "",
                get_out_of_stock_answer(store_data),
                "",
                get_low_stock_answer(store_data),
                "",
                get_top_selling_answer(store_data),
            ]

            message = "\n".join(sections)

            recipients = AuthorizedTelegramUser.objects.filter(
                is_active=True,
                linked_user__is_superuser=True,
            )

            if not recipients.exists():

                self.stdout.write(
                    self.style.WARNING(
                        "No authorized Telegram users to send to."
                    )
                )

                return

            sent_count = 0

            for recipient in recipients:

                response = send_telegram_message(
                    message,
                    chat_id=recipient.telegram_chat_id,
                )

                if response.status_code == 200:
                    sent_count += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Telegram failed for "
                            f"{recipient.telegram_chat_id}: "
                            f"{response.status_code}"
                        )
                    )

            if sent_count > 0:

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Daily summary sent to {sent_count} recipient(s)."
                    )
                )

                system_settings.last_daily_report_sent = today
                system_settings.save()

        except Exception as e:

            self.stdout.write(
                self.style.ERROR(
                    f"Daily summary failed: {e}"
                )
            )

    # ==========================================================
    # AI REPORT
    # ==========================================================

    def send_ai_report(self, system_settings, today):

        self.stdout.write("Generating AI report...")

        try:

            ai_report, telegram_response = generate_report()

            if telegram_response.status_code == 200:

                self.stdout.write(
                    self.style.SUCCESS(
                        "AI report sent successfully."
                    )
                )

                system_settings.last_ai_report_sent = today
                system_settings.save()

            else:

                self.stdout.write(
                    self.style.ERROR(
                        f"Telegram failed: "
                        f"{telegram_response.status_code}"
                    )
                )

        except Exception as e:

            self.stdout.write(
                self.style.ERROR(
                    f"AI report failed: {e}"
                )
            )
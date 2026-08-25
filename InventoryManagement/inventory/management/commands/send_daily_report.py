
from django.core.management.base import BaseCommand

from ...ai_report import generate_report


class Command(BaseCommand):

    help = "Generate and send the daily Telegram business report"

    def handle(self, *args, **options):

        self.stdout.write(
            "Generating daily business report..."
        )

        try:

            ai_report, telegram_response = generate_report()

            if telegram_response.status_code == 200:

                self.stdout.write(
                    self.style.SUCCESS(
                        "Daily report sent successfully."
                    )
                )

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
                    f"Daily report failed: {e}"
                )
            )


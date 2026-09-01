from django.conf import settings
from django.core.mail import send_mail as django_send_mail
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException


def send_notification_email(subject, message, recipient_email, recipient_name=""):
    """
    Sends an email using SMTP locally, and Brevo's HTTP API in production
    (Render blocks outbound SMTP ports, so a normal SMTP connection
    never completes there).
    """
    if settings.IS_PRODUCTION:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = settings.BREVO_API_KEY

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": recipient_email, "name": recipient_name}],
            sender={"email": settings.EMAIL_ACCOUNT, "name": "SoftCode Company"},
            subject=subject,
            text_content=message,
        )

        try:
            api_instance.send_transac_email(send_smtp_email)
        except ApiException as e:
            print(f"Brevo API error: {e}")
    else:
        django_send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient_email],
            fail_silently=False,
        )
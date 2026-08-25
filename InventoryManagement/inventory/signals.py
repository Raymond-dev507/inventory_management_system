from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import ActivityLog


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):

    ActivityLog.objects.create(
        user=user,
        action="LOGIN",
        description="Logged into the system"
    )
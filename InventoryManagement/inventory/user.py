from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .form import CreateUserForm, EditUserForm, SystemSettingsForm
from django.contrib import messages
from .user_helpers import can_edit_user
from .models import UserDeletionRecord, SystemSettings, ActivityLog
from .views import catch_up_stock_deduction


@login_required
@permission_required("auth.view_user", raise_exception=True)
def users(request):

    users = User.objects.prefetch_related("groups").order_by("-date_joined")

    if not request.user.is_superuser:
        users = users.exclude(is_superuser=True)

    show_deleted = (
        request.user.is_superuser
        and request.GET.get("show_deleted") == "1"
    )

    if show_deleted:
        users = users.filter(deletion_record__isnull=False)
    else:
        users = users.filter(deletion_record__isnull=True)

    total_users = users.count()
    active_users = users.filter(is_active=True).count()
    staff_group = Group.objects.filter(name__iexact="staff").first()

    staff_users = (
        staff_group.user_set.count()
        if staff_group
        else 0
    )

    return render(request, "users.html", {
        "users": users,
        "total_users": total_users,
        "active_users": active_users,
        "staff_users": staff_users,
        "show_deleted": show_deleted,
    })


@login_required
@permission_required("auth.add_user", raise_exception=True)
def add_user(request):

    if request.method == "POST":

        form = CreateUserForm(
            request.POST,
            request=request
        )

        if form.is_valid():

            user = form.save()

            messages.success(
                request,
                f"User '{user.username}' was created successfully."
            )

            return redirect("users")

    else:

        form = CreateUserForm(
            request=request
        )

    return render(
        request,
        "add_users.html",
        {
            "form": form
        }
    )


def _get_editable_user_or_404(request, user_id):

    queryset = User.objects.all()

    if not request.user.is_superuser:
        queryset = queryset.exclude(
            is_superuser=True
        ).filter(
            deletion_record__isnull=True
        )

    return get_object_or_404(queryset, id=user_id)


@login_required
@permission_required("auth.change_user", raise_exception=True)
def edit_user(request, user_id):

    current_user = request.user
    user = _get_editable_user_or_404(request, user_id)

    if not current_user.is_superuser and not can_edit_user(current_user, user):

        messages.error(
            request,
            "You cannot edit a user with equal or higher authority."
        )

        return redirect("users")

    if request.method == "POST":

        form = EditUserForm(
            request.POST,
            instance=user,
            request=request
        )

        if form.is_valid():

            updated_user = form.save()

            messages.success(
                request,
                f"User '{updated_user.username}' was updated successfully."
            )

            return redirect("users")

    else:

        form = EditUserForm(
            instance=user,
            request=request
        )

    return render(
        request,
        "edit_users.html",
        {
            "form": form,
            "user_account": user,
        }
    )


@login_required
@permission_required("auth.change_user", raise_exception=True)
@require_POST
def deactivate_user(request, user_id):

    current_user = request.user
    user = _get_editable_user_or_404(request, user_id)

    if user == current_user:

        messages.error(
            request,
            "You cannot deactivate your own account."
        )

        return redirect("users")

    if not current_user.is_superuser and not can_edit_user(current_user, user):

        messages.error(
            request,
            "You cannot deactivate a user with equal or higher authority."
        )

        return redirect("users")

    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])

    if user.is_active:
        messages.success(request, f"User '{user.username}' was reactivated.")
    else:
        messages.success(request, f"User '{user.username}' was deactivated.")

    return redirect("users")


@login_required
@permission_required("auth.delete_user", raise_exception=True)
@require_POST
def delete_user(request, user_id):

    current_user = request.user
    user = _get_editable_user_or_404(request, user_id)

    if user == current_user:

        messages.error(
            request,
            "You cannot delete your own account."
        )

        return redirect("users")

    if not current_user.is_superuser and not can_edit_user(current_user, user):

        messages.error(
            request,
            "You cannot delete a user with equal or higher authority."
        )

        return redirect("users")

    if hasattr(user, "deletion_record"):

        messages.info(
            request,
            f"User '{user.username}' was already deleted."
        )

        return redirect("users")

    user.is_active = False
    user.save(update_fields=["is_active"])

    UserDeletionRecord.objects.create(
        user=user,
        deleted_by=current_user,
    )

    messages.success(
        request,
        f"User '{user.username}' was deleted."
    )

    return redirect("users")


@login_required
@permission_required("auth.change_user", raise_exception=True)
@require_POST
def restore_user(request, user_id):

    if not request.user.is_superuser:

        messages.error(
            request,
            "Only the store owner can restore a deleted user."
        )

        return redirect("users")

    user = get_object_or_404(User, id=user_id)

    if not hasattr(user, "deletion_record"):

        messages.info(
            request,
            f"User '{user.username}' isn't deleted."
        )

        return redirect("users")

    user.deletion_record.delete()

    user.is_active = True
    user.save(update_fields=["is_active"])

    messages.success(
        request,
        f"User '{user.username}' was restored."
    )

    return redirect(f"{reverse('users')}?show_deleted=1")


@login_required
@permission_required("inventory.change_systemsettings", raise_exception=True)
def settings_view(request):

    settings_obj = SystemSettings.load()

    if request.method == "POST":

        # --------------------------------------------------
        # CAPTURE THE OLD VALUE BEFORE THE FORM OVERWRITES IT
        #
        # This is the only way to detect "it was just turned
        # on" versus "it was already on" — once form.save()
        # runs, the old value is gone.
        # --------------------------------------------------

        was_auto_deduct_enabled = settings_obj.auto_deduct_stock

        form = SystemSettingsForm(
            request.POST,
            instance=settings_obj
        )

        if form.is_valid():

            form.save()

            is_auto_deduct_enabled_now = form.instance.auto_deduct_stock

            # ------------------------------------------------
            # CATCH UP PENDING STOCK DEDUCTIONS
            #
            # Only runs on the False -> True transition. If it
            # was already True, or is being turned off, there
            # is nothing to catch up.
            # ------------------------------------------------

            if is_auto_deduct_enabled_now and not was_auto_deduct_enabled:

                caught_up_items = catch_up_stock_deduction()

                if caught_up_items:

                    product_details = "; ".join(
                        f"{item['product_name']} "
                        f"({item['quantity']} sold, "
                        f"stock {item['old_stock']} → {item['new_stock']})"
                        for item in caught_up_items
                    )

                    messages.success(
                        request,
                        f"Auto-deduct is back on. "
                        f"Updated stock for {len(caught_up_items)} "
                        f"previous sale item(s): {product_details}."
                    )

                    ActivityLog.objects.create(
                        user=request.user,
                        action="STOCK",
                        description=(
                            f"Auto-deduct was re-enabled. "
                            f"Stock catch-up processed "
                            f"{len(caught_up_items)} previous sale item(s)."
                        )
                    )

                else:

                    messages.success(
                        request,
                        "Auto-deduct is back on. "
                        "No pending stock deductions were found."
                    )

            else:

                messages.success(
                    request,
                    "Settings updated successfully."
                )

            return redirect("settings")

        messages.error(
            request,
            "Please correct the errors below."
        )

    else:

        form = SystemSettingsForm(
            instance=settings_obj
        )

    context = {
        "form": form,
        "settings": settings_obj,
    }

    return render(
        request,
        "settings.html",
        context
    )
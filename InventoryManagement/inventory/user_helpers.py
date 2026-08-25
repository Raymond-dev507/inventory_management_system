ROLE_HIERARCHY = {
    "sales": 1,
    "cashier": 2,
    "staff": 3,
    "manager": 4,
}


def get_user_role_level(user):
    """
    Return the highest role level belonging to the user.
    Superusers are treated as the highest authority.
    """

    if user.is_superuser:
        return 999

    highest_level = 0

    for group in user.groups.all():

        level = ROLE_HIERARCHY.get(
            group.name.lower(),
            0
        )

        highest_level = max(
            highest_level,
            level
        )

    return highest_level


def get_group_role_level(group):
    """
    Return the authority level of a group.
    """

    return ROLE_HIERARCHY.get(
        group.name.lower(),
        0
    )


def can_assign_group(current_user, group):
    """
    Determine whether current_user can assign this group.
    """

    if current_user.is_superuser:
        return True

    current_level = get_user_role_level(
        current_user
    )

    target_level = get_group_role_level(
        group
    )

    # Unknown/high-level groups are not assignable
    # by normal users.
    if target_level == 0:
        return False

    # A user can ONLY assign a role below their
    # own authority.
    return target_level < current_level


def can_edit_user(current_user, target_user):
    """
    Determine whether current_user can edit target_user.
    """

    # Nobody can edit a superuser
    # through this user-management system.
    if target_user.is_superuser:
        return False

    # Superuser can edit normal users.
    if current_user.is_superuser:
        return True

    current_level = get_user_role_level(current_user)
    target_level = get_user_role_level(target_user)

    # Cannot edit equal or higher authority.
    return target_level < current_level
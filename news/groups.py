"""Role names, group names and the permissions each role's group receives.

This module deliberately imports nothing from ``news.models`` so that the
models can import it without creating a circular import.

``ROLE_GROUP_NAMES`` maps a role value (``"reader"``, ``"editor"``,
``"journalist"``) to its group name, and ``ROLE_PERMISSIONS`` lists the
permission codenames each group receives.
"""
from django.contrib.auth.models import Group, Permission

READER = "reader"
EDITOR = "editor"
JOURNALIST = "journalist"

ROLE_GROUP_NAMES = {
    READER: "Reader",
    EDITOR: "Editor",
    JOURNALIST: "Journalist",
}

_VIEW = ["view_article", "view_newsletter"]
_MANAGE = [
    "view_article", "change_article", "delete_article",
    "view_newsletter", "change_newsletter", "delete_newsletter",
]

ROLE_PERMISSIONS = {
    # Readers can only view articles and newsletters.
    READER: _VIEW,
    # Editors can view, update and delete articles and newsletters, approve
    # articles and manage publishers - but not write articles.
    EDITOR: _MANAGE + [
        "approve_article",
        "view_publisher", "add_publisher", "change_publisher",
        "delete_publisher",
    ],
    # Journalists can create, view, update and delete.
    JOURNALIST: _MANAGE + ["add_article", "add_newsletter"],
}


def setup_role_groups():
    """Create the three role groups and assign their permissions.

    Safe to run repeatedly: groups are fetched or created and their
    permission sets are replaced with the definitions above. It runs
    automatically after every ``migrate`` (see :mod:`news.signals`).

    :returns: ``None``.
    """
    for role, codenames in ROLE_PERMISSIONS.items():
        group, _created = Group.objects.get_or_create(
            name=ROLE_GROUP_NAMES[role]
        )
        permissions = Permission.objects.filter(
            content_type__app_label="news", codename__in=codenames
        )
        group.permissions.set(permissions)

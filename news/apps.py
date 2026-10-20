"""Application configuration for the news app."""
from django.apps import AppConfig
from django.db.models.signals import post_migrate


class NewsConfig(AppConfig):
    """Registers signal handlers when Django starts."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "news"

    def ready(self):
        """Connect signals and create the role groups after migrating."""
        from . import signals

        # ``django.contrib.auth`` is listed before this app, so its
        # post_migrate handler has already created our model permissions
        # by the time this one runs.
        post_migrate.connect(signals.create_role_groups, sender=self)

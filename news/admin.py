"""Django admin configuration."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import (
    ApprovedArticleLog, Article, CustomUser, Newsletter, Publisher,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin for users, exposing the role and subscription fields."""

    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    list_display = ("username", "email", "role", "is_staff")
    list_filter = UserAdmin.list_filter + ("role",)
    fieldsets = UserAdmin.fieldsets + (
        ("News profile", {"fields": (
            "role", "subscribed_publishers", "subscribed_journalists",
        )}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("News profile", {"fields": ("email", "role")}),
    )

    def save_related(self, request, form, formsets, change):
        """Re-sync the role group after the form's M2M data is saved.

        The admin form saves the ``groups`` field after the model's own
        ``save()``, which could otherwise leave a user in the wrong group.
        """
        super().save_related(request, form, formsets, change)
        form.instance.sync_role_group()


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    """Admin for publishers."""

    list_display = ("name",)
    search_fields = ("name",)
    filter_horizontal = ("editors", "journalists")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Admin for articles, with a filter for the approval queue."""

    list_display = ("title", "author", "publisher", "approved", "created_at")
    list_filter = ("approved", "publisher")
    search_fields = ("title", "content")


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    """Admin for newsletters."""

    list_display = ("title", "author", "created_at")
    filter_horizontal = ("articles",)


@admin.register(ApprovedArticleLog)
class ApprovedArticleLogAdmin(admin.ModelAdmin):
    """Read-only view of articles received by the approval endpoint."""

    list_display = ("title", "article", "received_at")
    readonly_fields = ("article", "title", "payload", "received_at")

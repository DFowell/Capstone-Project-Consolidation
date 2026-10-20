"""Database models for the news application.

Normalisation notes (see DESIGN.md for the full ERD):
  * Every non-key column depends only on its table's primary key (3NF).
  * Many-to-many relationships (editors, journalists, subscriptions and
    newsletter contents) live in Django-managed link tables instead of
    comma-separated columns.
  * "Independent" articles are not stored separately: an article with no
    publisher is independent, so the information is never duplicated.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from .groups import ROLE_GROUP_NAMES


class CustomUser(AbstractUser):
    """A site user with a role (reader, editor or journalist)."""

    class Role(models.TextChoices):
        """The roles a user can hold. Each role maps to one group."""

        READER = "reader", "Reader"
        EDITOR = "editor", "Editor"
        JOURNALIST = "journalist", "Journalist"

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.READER
    )

    # Reader-only fields. They are emptied automatically for other roles.
    subscribed_publishers = models.ManyToManyField(
        "Publisher",
        blank=True,
        related_name="subscribers",
        help_text="Publishers this reader follows.",
    )
    subscribed_journalists = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="subscribers",
        limit_choices_to={"role": Role.JOURNALIST},
        help_text="Journalists this reader follows.",
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    # -- Role helpers -------------------------------------------------------
    @property
    def is_reader(self):
        """Return True if the user has the Reader role."""
        return self.role == self.Role.READER

    @property
    def is_editor(self):
        """Return True if the user has the Editor role."""
        return self.role == self.Role.EDITOR

    @property
    def is_journalist(self):
        """Return True if the user has the Journalist role."""
        return self.role == self.Role.JOURNALIST

    # -- Role-specific "fields" --------------------------------------------
    # Journalist content is a reverse relation (Article.author and
    # Newsletter.author). The properties below return None when the field
    # does not apply to the user's role, as the specification requires.
    @property
    def independent_articles(self):
        """Articles this journalist published without a publisher."""
        if not self.is_journalist:
            return None
        return self.articles.filter(publisher__isnull=True)

    @property
    def independent_newsletters(self):
        """Newsletters this journalist published."""
        if not self.is_journalist:
            return None
        return self.newsletters.all()

    @property
    def publisher_subscriptions(self):
        """The reader's publisher subscriptions (None for non-readers)."""
        if not self.is_reader:
            return None
        return self.subscribed_publishers.all()

    @property
    def journalist_subscriptions(self):
        """The reader's journalist subscriptions (None for non-readers)."""
        if not self.is_reader:
            return None
        return self.subscribed_journalists.all()

    # -- Persistence --------------------------------------------------------
    def save(self, *args, **kwargs):
        """Save the user, then keep group membership and fields in step."""
        super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "role" not in update_fields:
            # e.g. Django updating ``last_login``: the role cannot have
            # changed, so skip the extra group queries on every login.
            return
        self.sync_role_group()
        if not self.is_reader:
            # Reader-only data is cleared, mirroring the "None" rule.
            self.subscribed_publishers.clear()
            self.subscribed_journalists.clear()

    def sync_role_group(self):
        """Put the user in the group matching their role and no other."""
        target_name = ROLE_GROUP_NAMES[self.role]
        other_groups = Group.objects.filter(
            name__in=ROLE_GROUP_NAMES.values()
        ).exclude(name=target_name)
        self.groups.remove(*other_groups)
        group, _created = Group.objects.get_or_create(name=target_name)
        self.groups.add(group)


class Publisher(models.Model):
    """An organisation that employs editors and journalists."""

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    editors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="edited_publishers",
        limit_choices_to={"role": CustomUser.Role.EDITOR},
    )
    journalists = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="publishers",
        limit_choices_to={"role": CustomUser.Role.JOURNALIST},
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Article(models.Model):
    """A news article written by a journalist.

    An article with ``publisher`` set is publisher content; with no
    publisher it is an independent article.
    """

    title = models.CharField(max_length=255)
    content = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="articles",
        limit_choices_to={"role": CustomUser.Role.JOURNALIST},
    )
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_articles",
    )

    class Meta:
        ordering = ["-created_at"]
        permissions = [("approve_article", "Can approve articles")]
        indexes = [
            models.Index(
                fields=["approved", "-created_at"],
                name="news_art_appr_created_idx",
            )
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        """Return the article's page (used by the create/update views)."""
        return reverse("news:article_detail", args=[self.pk])

    @property
    def is_independent(self):
        """Return True if the article has no publisher."""
        return self.publisher_id is None

    def clean(self):
        """Validate the author's role and publisher membership."""
        if not self.author_id:
            return
        # Non-field errors are used on purpose: forms that omit the author
        # or publisher field (e.g. the editor's edit form) cannot display
        # an error attached to a field they do not contain.
        if not self.author.is_journalist:
            raise ValidationError(
                "Articles can only be written by journalists."
            )
        if self.publisher_id and not self.publisher.journalists.filter(
            pk=self.author_id
        ).exists():
            raise ValidationError(
                "The author is not a journalist at this publisher."
            )


class Newsletter(models.Model):
    """A curated collection of articles created by a journalist."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="newsletters",
        limit_choices_to={"role": CustomUser.Role.JOURNALIST},
    )
    articles = models.ManyToManyField(
        Article, blank=True, related_name="newsletters"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        """Return the newsletter's page (used by the create/update views)."""
        return reverse("news:newsletter_detail", args=[self.pk])


class ApprovedArticleLog(models.Model):
    """A record of an approved article received by ``/api/approved/``."""

    article = models.ForeignKey(
        Article,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_logs",
    )
    title = models.CharField(max_length=255)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"Approved: {self.title}"

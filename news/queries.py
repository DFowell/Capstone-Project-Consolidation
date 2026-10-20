"""Reusable article queries shared by the web views and the REST API."""
from django.db.models import Q

from .models import Article


def article_queryset():
    """Base queryset with related rows fetched in one go."""
    return Article.objects.select_related("author", "publisher")


def approved_articles():
    """All articles an editor has approved."""
    return article_queryset().filter(approved=True)


def subscribed_articles(user):
    """Approved articles from the publishers/journalists a reader follows.

    Users who are not readers have no subscriptions, so they get nothing.
    """
    if not user.is_authenticated or not user.is_reader:
        return Article.objects.none()
    return approved_articles().filter(
        Q(publisher__in=user.subscribed_publishers.all())
        | Q(author__in=user.subscribed_journalists.all())
    ).distinct()

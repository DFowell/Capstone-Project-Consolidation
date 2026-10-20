"""Reusable article queries shared by the web views and the REST API."""
from django.db.models import Q

from .models import Article


def article_queryset():
    """Return the base article queryset.

    Authors and publishers are fetched in the same query (``select_related``)
    so list pages do not run one extra query per article.

    :returns: a queryset of :class:`news.models.Article`.
    """
    return Article.objects.select_related("author", "publisher")


def approved_articles():
    """Return every article an editor has approved.

    :returns: a queryset of approved :class:`news.models.Article` objects,
        newest first.
    """
    return article_queryset().filter(approved=True)


def subscribed_articles(user):
    """Approved articles from the publishers/journalists a reader follows.

    Users who are not readers have no subscriptions, so they get nothing.
    An article matching both a publisher and a journalist subscription is
    returned only once.

    :param user: the (authenticated) user whose subscriptions to use.
    :returns: a queryset of approved articles, possibly empty.
    """
    if not user.is_authenticated or not user.is_reader:
        return Article.objects.none()
    return approved_articles().filter(
        Q(publisher__in=user.subscribed_publishers.all())
        | Q(author__in=user.subscribed_journalists.all())
    ).distinct()

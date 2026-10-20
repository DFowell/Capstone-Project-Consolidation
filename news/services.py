"""Side effects that run when an article is approved.

Kept separate from the signal handlers so the logic is easy to test and to
reuse from a view if the signal approach is ever swapped for "Option 2".
"""
import logging
from smtplib import SMTPException

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.db.models import Q
from django.urls import reverse

logger = logging.getLogger(__name__)


def get_subscriber_emails(article):
    """Return e-mail addresses of readers following the article's source.

    A reader qualifies if they subscribe to the article's author or to its
    publisher (when it has one). Readers without an address are skipped.
    """
    user_model = get_user_model()
    criteria = Q(subscribed_journalists=article.author)
    if article.publisher_id:
        criteria |= Q(subscribed_publishers=article.publisher)
    readers = (
        user_model.objects.filter(criteria, role=user_model.Role.READER)
        .exclude(email="")
        .distinct()
    )
    return list(readers.values_list("email", flat=True))


def send_approval_email(article):
    """E-mail the approved article to its subscribers.

    Returns the number of recipients. Delivery errors are logged rather
    than raised so a mail outage cannot block an editor's approval.
    """
    recipients = get_subscriber_emails(article)
    if not recipients:
        return 0

    source = article.publisher.name if article.publisher_id else "independent"
    link = settings.SITE_URL + reverse(
        "news:article_detail", args=[article.pk]
    )
    body = (
        f"{article.title}\n"
        f"By {article.author.get_username()} ({source})\n\n"
        f"{article.content}\n\n"
        f"Read it online: {link}\n"
    )
    message = EmailMessage(
        subject=f"New article: {article.title}",
        body=body,
        to=[settings.DEFAULT_FROM_EMAIL],
        bcc=recipients,  # hide subscribers' addresses from each other
    )
    try:
        message.send()
    except (SMTPException, OSError):
        logger.exception("Could not e-mail article %s", article.pk)
        return 0
    return len(recipients)


def build_approval_payload(article):
    """Return the JSON-serialisable dict sent to ``/api/approved/``."""
    return {
        "article_id": article.pk,
        "title": article.title,
        "content": article.content,
        "author": article.author.get_username(),
        "publisher": article.publisher.name if article.publisher_id else None,
        "approved_by": (
            article.approved_by.get_username()
            if article.approved_by_id else None
        ),
        "created_at": article.created_at.isoformat(),
    }


def post_approved_article(article):
    """POST the approved article to our own RESTful endpoint.

    Returns True on success. Network problems are logged, not raised.
    """
    if not settings.APPROVED_API_URL:
        return False
    try:
        response = requests.post(
            settings.APPROVED_API_URL,
            json=build_approval_payload(article),
            headers={"X-Internal-Token": settings.APPROVED_API_TOKEN},
            timeout=settings.APPROVED_API_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.warning(
            "Could not POST approved article %s to %s",
            article.pk, settings.APPROVED_API_URL, exc_info=True,
        )
        return False
    return True

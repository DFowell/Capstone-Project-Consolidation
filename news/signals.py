"""Signal handlers (implementation strategy "Option 1" from the brief).

* ``pre_save``/``post_save`` on ``Article`` detect the moment an article
  becomes approved and trigger the e-mail and the POST to ``/api/approved/``.
* ``m2m_changed`` keeps reader subscriptions reader-only.
* ``create_role_groups`` builds the Reader/Editor/Journalist groups.
"""
from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from .groups import setup_role_groups
from .models import Article, CustomUser
from .services import post_approved_article, send_approval_email


def create_role_groups(sender, **kwargs):
    """post_migrate handler: create role groups and their permissions."""
    setup_role_groups()


@receiver(pre_save, sender=Article)
def remember_previous_approval(sender, instance, **kwargs):
    """Record whether the article was already approved before this save."""
    if instance.pk:
        instance._was_approved = Article.objects.filter(
            pk=instance.pk, approved=True
        ).exists()
    else:
        instance._was_approved = False


@receiver(post_save, sender=Article)
def handle_article_approval(sender, instance, raw=False, **kwargs):
    """Notify subscribers when an article changes to approved.

    Saving an already-approved article again does nothing, so editing the
    text later never re-sends the e-mail.
    """
    if raw or not instance.approved:
        return
    if getattr(instance, "_was_approved", False):
        return
    send_approval_email(instance)
    post_approved_article(instance)
    instance._was_approved = True


def _purge_non_reader_subscriptions(sender, instance, action, reverse,
                                    pk_set, field_name, **kwargs):
    """Remove subscriptions that were just added for non-readers."""
    if action != "post_add" or not pk_set:
        return
    if not reverse:
        if not instance.is_reader:
            getattr(instance, field_name).clear()
        return
    # Reverse side: ``instance`` is the publisher/journalist and ``pk_set``
    # holds subscriber ids. Drop any subscribers who are not readers.
    user_model = get_user_model()
    invalid = user_model.objects.filter(pk__in=pk_set).exclude(
        role=user_model.Role.READER
    )
    instance.subscribers.remove(*invalid)


@receiver(m2m_changed, sender=CustomUser.subscribed_publishers.through)
def enforce_reader_publisher_subscriptions(sender, **kwargs):
    """Only readers may subscribe to publishers."""
    _purge_non_reader_subscriptions(
        sender, field_name="subscribed_publishers", **kwargs
    )


@receiver(m2m_changed, sender=CustomUser.subscribed_journalists.through)
def enforce_reader_journalist_subscriptions(sender, **kwargs):
    """Only readers may subscribe to journalists."""
    _purge_non_reader_subscriptions(
        sender, field_name="subscribed_journalists", **kwargs
    )

"""Tests for the approval signal (e-mail + POST to /api/approved/)."""
from django.conf import settings
from django.core import mail
from requests import ConnectionError as RequestsConnectionError

from news.services import build_approval_payload, get_subscriber_emails

from .base import NewsTestCase


class ApprovalSignalTests(NewsTestCase):
    """Approving an article notifies subscribers exactly once."""

    def setUp(self):
        super().setUp()
        # Follows the publisher only.
        self.publisher_fan = self.make_user("pubfan", self.reader.Role.READER)
        self.publisher_fan.subscribed_publishers.add(self.publisher)
        # Follows the journalist only.
        self.journalist_fan = self.make_user("jfan", self.reader.Role.READER)
        self.journalist_fan.subscribed_journalists.add(self.journalist)
        # Follows someone else entirely.
        self.bystander = self.make_user("bystander", self.reader.Role.READER)
        self.bystander.subscribed_publishers.add(self.other_publisher)
        mail.outbox.clear()

    def approve(self, article):
        """Approve an article the way the editor view does."""
        article.approved = True
        article.approved_by = self.editor
        article.save()

    def test_publisher_article_emails_publisher_and_journalist_fans(self):
        article = self.make_article(
            "Breaking", self.journalist, self.publisher
        )
        self.approve(article)
        self.assertEqual(len(mail.outbox), 1)
        recipients = set(mail.outbox[0].bcc)
        self.assertEqual(recipients, {"pubfan@example.com",
                                      "jfan@example.com"})
        self.assertIn("Breaking", mail.outbox[0].subject)

    def test_independent_article_emails_only_journalist_fans(self):
        article = self.make_article("Solo story", self.journalist)
        self.approve(article)
        self.assertEqual(set(mail.outbox[0].bcc), {"jfan@example.com"})

    def test_non_subscribers_are_not_emailed(self):
        article = self.make_article("Breaking", self.journalist,
                                    self.publisher)
        self.approve(article)
        self.assertNotIn("bystander@example.com", mail.outbox[0].bcc)

    def test_reader_following_both_is_emailed_once(self):
        self.journalist_fan.subscribed_publishers.add(self.publisher)
        article = self.make_article("Breaking", self.journalist,
                                    self.publisher)
        self.approve(article)
        self.assertEqual(mail.outbox[0].bcc.count("jfan@example.com"), 1)

    def test_approval_posts_article_to_api_endpoint(self):
        article = self.make_article("Breaking", self.journalist,
                                    self.publisher)
        self.approve(article)
        self.mock_post.assert_called_once()
        args, kwargs = self.mock_post.call_args
        self.assertEqual(args[0], settings.APPROVED_API_URL)
        self.assertEqual(kwargs["json"]["title"], "Breaking")
        self.assertEqual(kwargs["json"]["publisher"], "Daily Planet")
        self.assertEqual(kwargs["json"]["approved_by"], "editor")
        self.assertEqual(
            kwargs["headers"]["X-Internal-Token"],
            settings.APPROVED_API_TOKEN,
        )

    def test_saving_unapproved_article_triggers_nothing(self):
        article = self.make_article("Draft", self.journalist)
        article.title = "Draft v2"
        article.save()
        self.assertEqual(len(mail.outbox), 0)
        self.mock_post.assert_not_called()

    def test_resaving_approved_article_does_not_resend(self):
        article = self.make_article("Breaking", self.journalist,
                                    self.publisher)
        self.approve(article)
        article.title = "Breaking (updated)"
        article.save()
        refreshed = type(article).objects.get(pk=article.pk)
        refreshed.content = "Edited again"
        refreshed.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.mock_post.call_count, 1)

    def test_article_created_already_approved_triggers_notification(self):
        self.make_article("Instant", self.journalist, self.publisher,
                          approved=True)
        self.assertEqual(len(mail.outbox), 1)
        self.mock_post.assert_called_once()

    def test_no_subscribers_means_no_email_but_still_posts(self):
        article = self.make_article("Other", self.other_journalist)
        self.approve(article)
        self.assertEqual(len(mail.outbox), 0)
        self.mock_post.assert_called_once()

    def test_api_failure_does_not_break_approval_or_email(self):
        self.mock_post.side_effect = RequestsConnectionError("down")
        article = self.make_article("Breaking", self.journalist,
                                    self.publisher)
        with self.assertLogs("news.services", level="WARNING"):
            self.approve(article)
        article.refresh_from_db()
        self.assertTrue(article.approved)
        self.assertEqual(len(mail.outbox), 1)


class ServiceHelperTests(NewsTestCase):
    """Small unit tests for the helper functions."""

    def test_readers_without_email_are_skipped(self):
        fan = self.make_user("noemail", self.reader.Role.READER)
        fan.email = ""
        fan.save()
        fan.subscribed_journalists.add(self.journalist)
        self.assertEqual(get_subscriber_emails(self.independent), [])

    def test_payload_marks_independent_articles_with_null_publisher(self):
        payload = build_approval_payload(self.independent)
        self.assertIsNone(payload["publisher"])
        self.assertEqual(payload["article_id"], self.independent.pk)

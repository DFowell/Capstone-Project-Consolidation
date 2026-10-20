"""Tests for the HTML views: access control, review queue, forms."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from news.models import Article, Newsletter, Publisher

from .base import PASSWORD, NewsTestCase

User = get_user_model()


class LoginRequiredTests(NewsTestCase):
    """Anonymous visitors are sent to the login page."""

    def test_protected_pages_redirect_anonymous_users(self):
        urls = [
            reverse("news:article_list"),
            reverse("news:article_create"),
            reverse("news:review_list"),
            reverse("news:newsletter_list"),
            reverse("news:article_detail", args=[self.independent.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)


class RegistrationTests(NewsTestCase):
    """Self-service sign-up."""

    def register(self, role):
        return self.client.post(reverse("news:register"), {
            "username": "newbie", "email": "newbie@example.com",
            "password1": PASSWORD, "password2": PASSWORD, "role": role,
        })

    def test_reader_can_register_and_is_logged_in(self):
        response = self.register("reader")
        self.assertRedirects(response, reverse("news:article_list"))
        user = User.objects.get(username="newbie")
        self.assertTrue(user.is_reader)
        self.assertEqual(
            list(user.groups.values_list("name", flat=True)), ["Reader"]
        )

    def test_journalist_can_register(self):
        self.register("journalist")
        user = User.objects.get(username="newbie")
        self.assertTrue(user.has_perm("news.add_article"))

    def test_editor_can_register_without_admin(self):
        response = self.register("editor")
        self.assertRedirects(response, reverse("news:article_list"))
        user = User.objects.get(username="newbie")
        self.assertTrue(user.is_editor)
        self.assertTrue(user.has_perm("news.approve_article"))
        self.assertFalse(user.is_staff)
        self.assertEqual(
            list(user.groups.values_list("name", flat=True)), ["Editor"]
        )

    def test_unknown_role_is_rejected(self):
        response = self.register("superuser")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(reverse("news:register"), {
            "username": "newbie", "email": "n@example.com",
            "password1": PASSWORD, "password2": "different", "role": "reader",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())


class ArticleListViewTests(NewsTestCase):
    """The home page lists approved articles only."""

    def test_reader_sees_approved_articles_only(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(reverse("news:article_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Independent scoop")
        self.assertNotContains(response, "Unapproved draft")

    def test_subscribed_filter_narrows_the_list(self):
        self.reader.subscribed_publishers.add(self.publisher)
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(
            reverse("news:article_list") + "?filter=subscribed"
        )
        self.assertContains(response, "Planet exclusive")
        self.assertNotContains(response, "Gazette report")
        self.assertNotContains(response, "Independent scoop")

    def test_empty_subscribed_filter_shows_helpful_message(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(
            reverse("news:article_list") + "?filter=subscribed"
        )
        self.assertContains(response, "Choose who to follow")


class ArticleDetailViewTests(NewsTestCase):
    """Single-article page rules."""

    def test_reader_can_open_approved_article(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(
            reverse("news:article_detail", args=[self.independent.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Delete")

    def test_reader_gets_404_for_unapproved_article(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(
            reverse("news:article_detail", args=[self.draft.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_author_sees_edit_buttons_on_own_draft(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.get(
            reverse("news:article_detail", args=[self.draft.pk])
        )
        self.assertContains(response, "Edit")
        self.assertContains(response, "Awaiting review")


class ArticleCreateViewTests(NewsTestCase):
    """Journalists create articles; others cannot."""

    def test_journalist_creates_unapproved_article(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.post(reverse("news:article_create"), {
            "title": "Fresh", "content": "Text", "publisher": "",
        })
        self.assertRedirects(
            response, reverse("news:article_detail",
                              args=[Article.objects.get(title="Fresh").pk]),
            fetch_redirect_response=False,
        )
        article = Article.objects.get(title="Fresh")
        self.assertEqual(article.author, self.journalist)
        self.assertFalse(article.approved)
        self.assertIsNone(article.publisher)

    def test_journalist_can_choose_own_publisher(self):
        self.client.login(username="jane", password=PASSWORD)
        self.client.post(reverse("news:article_create"), {
            "title": "Pub", "content": "Text",
            "publisher": self.publisher.pk,
        })
        self.assertEqual(Article.objects.get(title="Pub").publisher,
                         self.publisher)

    def test_journalist_cannot_choose_foreign_publisher(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.post(reverse("news:article_create"), {
            "title": "Bad", "content": "Text",
            "publisher": self.other_publisher.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Article.objects.filter(title="Bad").exists())

    def test_reader_gets_403(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(reverse("news:article_create"))
        self.assertEqual(response.status_code, 403)

    def test_editor_gets_403(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.get(reverse("news:article_create"))
        self.assertEqual(response.status_code, 403)

    def test_missing_title_shows_form_error(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.post(reverse("news:article_create"),
                                    {"title": "", "content": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")


class ArticleEditDeleteViewTests(NewsTestCase):
    """Update and delete rules on the web pages."""

    def test_editor_can_edit_any_article(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(
            reverse("news:article_update", args=[self.independent.pk]),
            {"title": "Edited", "content": "New text"},
        )
        self.assertEqual(response.status_code, 302)
        self.independent.refresh_from_db()
        self.assertEqual(self.independent.title, "Edited")
        self.assertEqual(self.independent.author, self.journalist)

    def test_journalist_can_edit_own_article(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.post(
            reverse("news:article_update", args=[self.draft.pk]),
            {"title": "Tweaked", "content": "Body", "publisher": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, "Tweaked")

    def test_journalist_cannot_edit_others_article(self):
        self.client.login(username="joe", password=PASSWORD)
        response = self.client.get(
            reverse("news:article_update", args=[self.independent.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_reader_cannot_edit(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(
            reverse("news:article_update", args=[self.independent.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_can_delete_article(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(
            reverse("news:article_delete", args=[self.independent.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Article.objects.filter(pk=self.independent.pk).exists()
        )

    def test_journalist_cannot_delete_others_article(self):
        self.client.login(username="joe", password=PASSWORD)
        response = self.client.post(
            reverse("news:article_delete", args=[self.independent.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            Article.objects.filter(pk=self.independent.pk).exists()
        )


class ReviewQueueTests(NewsTestCase):
    """Editors review and approve articles."""

    def test_editor_sees_only_unapproved_articles(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.get(reverse("news:review_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unapproved draft")
        self.assertNotContains(response, "Independent scoop")

    def test_reader_cannot_open_review_queue(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(reverse("news:review_list"))
        self.assertEqual(response.status_code, 403)

    def test_journalist_cannot_open_review_queue(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.get(reverse("news:review_list"))
        self.assertEqual(response.status_code, 403)

    def test_editor_can_approve_article(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(
            reverse("news:article_approve", args=[self.draft.pk])
        )
        self.assertRedirects(response, reverse("news:review_list"))
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.approved)
        self.assertEqual(self.draft.approved_by, self.editor)

    def test_approval_triggers_email_and_api_post(self):
        fan = self.make_user("fan", User.Role.READER)
        fan.subscribed_journalists.add(self.journalist)
        mail.outbox.clear()
        self.client.login(username="editor", password=PASSWORD)
        self.client.post(
            reverse("news:article_approve", args=[self.draft.pk])
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, ["fan@example.com"])
        self.mock_post.assert_called_once()

    def test_approving_twice_does_not_notify_twice(self):
        self.client.login(username="editor", password=PASSWORD)
        url = reverse("news:article_approve", args=[self.draft.pk])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(self.mock_post.call_count, 1)

    def test_journalist_cannot_approve(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.post(
            reverse("news:article_approve", args=[self.draft.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.approved)

    def test_reader_cannot_approve(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.post(
            reverse("news:article_approve", args=[self.draft.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_approve_requires_post(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.get(
            reverse("news:article_approve", args=[self.draft.pk])
        )
        self.assertEqual(response.status_code, 405)
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.approved)

    def test_approving_missing_article_gives_404(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(
            reverse("news:article_approve", args=[99999])
        )
        self.assertEqual(response.status_code, 404)


class SubscriptionViewTests(NewsTestCase):
    """Readers manage who they follow."""

    def test_reader_can_update_subscriptions(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.post(reverse("news:subscriptions"), {
            "subscribed_publishers": [self.publisher.pk],
            "subscribed_journalists": [self.journalist.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.reader.subscribed_publishers.all()),
                         [self.publisher])
        self.assertEqual(list(self.reader.subscribed_journalists.all()),
                         [self.journalist])

    def test_journalist_cannot_open_subscription_page(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.get(reverse("news:subscriptions"))
        self.assertEqual(response.status_code, 403)


class NewsletterViewTests(NewsTestCase):
    """Readers view; journalists create; editors and owners change."""

    def test_reader_can_view_newsletters(self):
        newsletter = self.make_newsletter(self.journalist,
                                          [self.independent])
        self.client.login(username="reader", password=PASSWORD)
        listing = self.client.get(reverse("news:newsletter_list"))
        detail = self.client.get(
            reverse("news:newsletter_detail", args=[newsletter.pk])
        )
        self.assertContains(listing, "Weekly digest")
        self.assertContains(detail, "Independent scoop")

    def test_newsletter_page_hides_articles_that_lost_approval(self):
        newsletter = self.make_newsletter(
            self.journalist, [self.independent, self.publisher_article]
        )
        Article.objects.filter(pk=self.publisher_article.pk).update(
            approved=False
        )
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(
            reverse("news:newsletter_detail", args=[newsletter.pk])
        )
        self.assertContains(response, "Independent scoop")
        self.assertNotContains(response, "Planet exclusive")

    def test_reader_cannot_create_newsletter(self):
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(reverse("news:newsletter_create"))
        self.assertEqual(response.status_code, 403)

    def test_journalist_creates_newsletter(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.post(reverse("news:newsletter_create"), {
            "title": "Digest", "description": "Best",
            "articles": [self.independent.pk],
        })
        self.assertEqual(response.status_code, 302)
        newsletter = Newsletter.objects.get(title="Digest")
        self.assertEqual(newsletter.author, self.journalist)
        self.assertEqual(list(newsletter.articles.all()),
                         [self.independent])

    def test_newsletter_form_rejects_unapproved_article(self):
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.post(reverse("news:newsletter_create"), {
            "title": "Digest", "articles": [self.draft.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Newsletter.objects.filter(title="Digest").exists())

    def test_editor_can_edit_and_delete_newsletter(self):
        newsletter = self.make_newsletter(self.journalist)
        self.client.login(username="editor", password=PASSWORD)
        edit = self.client.post(
            reverse("news:newsletter_update", args=[newsletter.pk]),
            {"title": "Retitled", "description": ""},
        )
        self.assertEqual(edit.status_code, 302)
        newsletter.refresh_from_db()
        self.assertEqual(newsletter.title, "Retitled")
        delete = self.client.post(
            reverse("news:newsletter_delete", args=[newsletter.pk])
        )
        self.assertEqual(delete.status_code, 302)
        self.assertFalse(Newsletter.objects.filter(pk=newsletter.pk).exists())

    def test_journalist_cannot_edit_others_newsletter(self):
        newsletter = self.make_newsletter(self.other_journalist)
        self.client.login(username="jane", password=PASSWORD)
        response = self.client.get(
            reverse("news:newsletter_update", args=[newsletter.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_reader_cannot_delete_newsletter(self):
        newsletter = self.make_newsletter(self.journalist)
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.post(
            reverse("news:newsletter_delete", args=[newsletter.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Newsletter.objects.filter(pk=newsletter.pk).exists())


class PublisherViewTests(NewsTestCase):
    """Editors create and manage publishers without the admin site."""

    def test_editor_creates_publisher_and_becomes_its_editor(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(reverse("news:publisher_create"), {
            "name": "New Times", "description": "Daily news",
            "journalists": [self.journalist.pk],
        })
        self.assertRedirects(response, reverse("news:publisher_list"))
        publisher = Publisher.objects.get(name="New Times")
        self.assertIn(self.editor, publisher.editors.all())
        self.assertIn(self.journalist, publisher.journalists.all())

    def test_duplicate_publisher_name_is_rejected(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(reverse("news:publisher_create"),
                                    {"name": "Daily Planet"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Publisher.objects.filter(name="Daily Planet").count(),
                         1)

    def test_form_only_offers_journalists_as_journalists(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(reverse("news:publisher_create"), {
            "name": "Odd", "journalists": [self.reader.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Publisher.objects.filter(name="Odd").exists())

    def test_reader_and_journalist_cannot_manage_publishers(self):
        for username in ("reader", "jane"):
            with self.subTest(user=username):
                self.client.login(username=username, password=PASSWORD)
                for name in ("publisher_list", "publisher_create"):
                    response = self.client.get(reverse(f"news:{name}"))
                    self.assertEqual(response.status_code, 403)

    def test_editor_of_publisher_can_add_a_journalist(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(
            reverse("news:publisher_update", args=[self.publisher.pk]),
            {"name": "Daily Planet", "editors": [self.editor.pk],
             "journalists": [self.journalist.pk, self.other_journalist.pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.publisher.journalists.count(), 2)

    def test_editor_of_another_publisher_cannot_change_it(self):
        self.make_user("outsider", User.Role.EDITOR)
        self.client.login(username="outsider", password=PASSWORD)
        response = self.client.get(
            reverse("news:publisher_update", args=[self.publisher.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_deleting_publisher_keeps_articles_as_independent(self):
        self.client.login(username="editor", password=PASSWORD)
        response = self.client.post(
            reverse("news:publisher_delete", args=[self.publisher.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.publisher_article.refresh_from_db()
        self.assertIsNone(self.publisher_article.publisher)

    def test_journalist_added_by_editor_can_write_for_publisher(self):
        self.publisher.journalists.add(self.other_journalist)
        self.client.login(username="joe", password=PASSWORD)
        self.client.post(reverse("news:article_create"), {
            "title": "Joe at the Planet", "content": "Text",
            "publisher": self.publisher.pk,
        })
        self.assertEqual(
            Article.objects.get(title="Joe at the Planet").publisher,
            self.publisher,
        )

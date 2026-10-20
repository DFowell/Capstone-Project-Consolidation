"""Tests for the REST API: auth, per-role access, subscriptions, CRUD."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from news.models import ApprovedArticleLog, Article, Newsletter

from .base import PASSWORD, NewsTestCase

User = get_user_model()


def titles(response):
    """Return the set of article titles in a list response."""
    return {item["title"] for item in response.data}


class TokenAuthTests(NewsTestCase):
    """Obtaining and using auth tokens."""

    def test_valid_credentials_return_token(self):
        response = APIClient().post(
            reverse("api-token"),
            {"username": "reader", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)

    def test_login_alias_returns_token(self):
        response = APIClient().post(
            reverse("api-login"),
            {"username": "jane", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_wrong_password_is_rejected(self):
        response = APIClient().post(
            reverse("api-token"),
            {"username": "reader", "password": "wrong"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("token", response.data)

    def test_request_without_token_is_unauthorised(self):
        response = APIClient().get(reverse("article-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_token_is_unauthorised(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
        response = client.get(reverse("article-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_endpoint_returns_profile(self):
        client = self.api_client_for(self.reader)
        response = client.get(reverse("api-me"))
        self.assertEqual(response.data["username"], "reader")
        self.assertEqual(response.data["role"], "reader")


class ArticleReadAccessTests(NewsTestCase):
    """Every authenticated role can read; only approved items are listed."""

    def test_each_role_can_list_articles(self):
        for user in (self.reader, self.editor, self.journalist):
            with self.subTest(role=user.role):
                response = self.api_client_for(user).get(
                    reverse("article-list")
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_contains_only_approved_articles(self):
        response = self.api_client_for(self.reader).get(
            reverse("article-list")
        )
        self.assertEqual(
            titles(response),
            {"Independent scoop", "Planet exclusive", "Gazette report"},
        )

    def test_list_hides_drafts_even_from_their_author(self):
        response = self.api_client_for(self.journalist).get(
            reverse("article-list")
        )
        self.assertNotIn("Unapproved draft", titles(response))

    def test_reader_can_retrieve_single_approved_article(self):
        response = self.api_client_for(self.reader).get(
            reverse("article-detail", args=[self.independent.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Independent scoop")
        self.assertEqual(response.data["author"]["username"], "jane")

    def test_reader_cannot_see_unapproved_article(self):
        response = self.api_client_for(self.reader).get(
            reverse("article-detail", args=[self.draft.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_editor_and_author_can_see_unapproved_article(self):
        for user in (self.editor, self.journalist):
            with self.subTest(role=user.role):
                response = self.api_client_for(user).get(
                    reverse("article-detail", args=[self.draft.pk])
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_other_journalist_cannot_see_unapproved_article(self):
        response = self.api_client_for(self.other_journalist).get(
            reverse("article-detail", args=[self.draft.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SubscribedArticlesTests(NewsTestCase):
    """GET /api/articles/subscribed/ follows the reader's subscriptions."""

    def test_reader_with_no_subscriptions_gets_nothing(self):
        response = self.api_client_for(self.reader).get(
            reverse("article-subscribed")
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_publisher_subscription_returns_publisher_articles(self):
        self.reader.subscribed_publishers.add(self.publisher)
        response = self.api_client_for(self.reader).get(
            reverse("article-subscribed")
        )
        self.assertEqual(titles(response), {"Planet exclusive"})

    def test_journalist_subscription_returns_all_their_approved_work(self):
        self.reader.subscribed_journalists.add(self.journalist)
        response = self.api_client_for(self.reader).get(
            reverse("article-subscribed")
        )
        self.assertEqual(
            titles(response), {"Independent scoop", "Planet exclusive"}
        )

    def test_combined_subscriptions_have_no_duplicates(self):
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.subscribed_journalists.add(self.journalist)
        response = self.api_client_for(self.reader).get(
            reverse("article-subscribed")
        )
        self.assertEqual(len(response.data), 2)

    def test_reader_only_retrieves_their_subscribed_content(self):
        self.reader.subscribed_publishers.add(self.other_publisher)
        response = self.api_client_for(self.reader).get(
            reverse("article-subscribed")
        )
        self.assertEqual(titles(response), {"Gazette report"})
        self.assertNotIn("Planet exclusive", titles(response))

    def test_unapproved_articles_never_appear(self):
        self.reader.subscribed_journalists.add(self.journalist)
        response = self.api_client_for(self.reader).get(
            reverse("article-subscribed")
        )
        self.assertNotIn("Unapproved draft", titles(response))

    def test_two_readers_see_their_own_subscriptions(self):
        second = self.make_user("reader2", User.Role.READER)
        self.reader.subscribed_publishers.add(self.publisher)
        second.subscribed_publishers.add(self.other_publisher)
        first_titles = titles(self.api_client_for(self.reader).get(
            reverse("article-subscribed")))
        second_titles = titles(self.api_client_for(second).get(
            reverse("article-subscribed")))
        self.assertEqual(first_titles, {"Planet exclusive"})
        self.assertEqual(second_titles, {"Gazette report"})

    def test_non_readers_have_no_subscribed_feed(self):
        response = self.api_client_for(self.journalist).get(
            reverse("article-subscribed")
        )
        self.assertEqual(response.data, [])


class JournalistCreateTests(NewsTestCase):
    """Only journalists can POST articles."""

    payload = {"title": "New story", "content": "Details."}

    def test_journalist_can_create_independent_article(self):
        response = self.api_client_for(self.journalist).post(
            reverse("article-list"), self.payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        article = Article.objects.get(pk=response.data["id"])
        self.assertEqual(article.author, self.journalist)
        self.assertIsNone(article.publisher)
        self.assertFalse(article.approved)

    def test_journalist_can_create_publisher_article(self):
        data = dict(self.payload, publisher=self.publisher.pk)
        response = self.api_client_for(self.journalist).post(
            reverse("article-list"), data, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["publisher"], self.publisher.pk)

    def test_author_cannot_be_spoofed(self):
        data = dict(self.payload, author=self.other_journalist.pk)
        response = self.api_client_for(self.journalist).post(
            reverse("article-list"), data, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["author"]["username"], "jane")

    def test_journalist_cannot_post_to_foreign_publisher(self):
        data = dict(self.payload, publisher=self.other_publisher.pk)
        response = self.api_client_for(self.journalist).post(
            reverse("article-list"), data, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("publisher", response.data)

    def test_journalist_cannot_self_approve_on_create(self):
        data = dict(self.payload, approved=True)
        response = self.api_client_for(self.journalist).post(
            reverse("article-list"), data, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Article.objects.filter(title="New story").exists())

    def test_missing_title_is_rejected(self):
        response = self.api_client_for(self.journalist).post(
            reverse("article-list"), {"content": "No title"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("title", response.data)

    def test_reader_cannot_create(self):
        response = self.api_client_for(self.reader).post(
            reverse("article-list"), self.payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_cannot_create(self):
        response = self.api_client_for(self.editor).post(
            reverse("article-list"), self.payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class UpdateAndApprovalTests(NewsTestCase):
    """PUT: editors approve; journalists edit their own work."""

    def put(self, user, article, **changes):
        """PUT the article's data (plus changes) as the given user."""
        data = {
            "title": article.title,
            "content": article.content,
            "publisher": article.publisher_id,
        }
        data.update(changes)
        return self.api_client_for(user).put(
            reverse("article-detail", args=[article.pk]), data,
            format="json",
        )

    def test_editor_can_approve_article(self):
        response = self.put(self.editor, self.draft, approved=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.approved)
        self.assertEqual(self.draft.approved_by, self.editor)

    def test_approving_via_api_notifies_subscribers(self):
        fan = self.make_user("fan", User.Role.READER)
        fan.subscribed_journalists.add(self.journalist)
        mail.outbox.clear()
        self.put(self.editor, self.draft, approved=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, ["fan@example.com"])
        self.mock_post.assert_called_once()

    def test_editor_can_unapprove_article(self):
        response = self.put(self.editor, self.independent, approved=False)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.independent.refresh_from_db()
        self.assertFalse(self.independent.approved)

    def test_journalist_cannot_approve_own_article(self):
        response = self.put(self.journalist, self.draft, approved=True)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.approved)
        self.mock_post.assert_not_called()

    def test_journalist_can_edit_own_article(self):
        response = self.put(self.journalist, self.draft, title="Better title")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, "Better title")
        self.assertFalse(self.draft.approved)

    def test_journalist_cannot_edit_someone_elses_article(self):
        response = self.put(self.other_journalist, self.independent,
                            title="Hijacked")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.independent.refresh_from_db()
        self.assertEqual(self.independent.title, "Independent scoop")

    def test_reader_cannot_update(self):
        response = self.put(self.reader, self.independent, title="Nope")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_edit_text(self):
        response = self.put(self.editor, self.independent,
                            content="Edited by editor")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.independent.refresh_from_db()
        self.assertEqual(self.independent.content, "Edited by editor")

    def test_partial_update_works(self):
        response = self.api_client_for(self.editor).patch(
            reverse("article-detail", args=[self.draft.pk]),
            {"approved": True}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.approved)


class DeleteTests(NewsTestCase):
    """DELETE: editors anywhere; journalists only their own."""

    def delete(self, user, article):
        """DELETE the article as the given user."""
        return self.api_client_for(user).delete(
            reverse("article-detail", args=[article.pk])
        )

    def test_editor_can_delete_any_article(self):
        response = self.delete(self.editor, self.other_article)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Article.objects.filter(pk=self.other_article.pk).exists()
        )

    def test_journalist_can_delete_own_article(self):
        response = self.delete(self.journalist, self.independent)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_journalist_cannot_delete_others_article(self):
        response = self.delete(self.journalist, self.other_article)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            Article.objects.filter(pk=self.other_article.pk).exists()
        )

    def test_reader_cannot_delete(self):
        response = self.delete(self.reader, self.independent)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            Article.objects.filter(pk=self.independent.pk).exists()
        )

    def test_deleting_missing_article_returns_404(self):
        response = self.api_client_for(self.editor).delete(
            reverse("article-detail", args=[99999])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NewsletterApiTests(NewsTestCase):
    """Newsletters behave correctly through the API."""

    def test_reader_can_list_and_view_newsletters(self):
        newsletter = self.make_newsletter(
            self.journalist, [self.independent]
        )
        client = self.api_client_for(self.reader)
        listing = client.get(reverse("newsletter-list"))
        detail = client.get(reverse("newsletter-detail",
                                    args=[newsletter.pk]))
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 1)
        self.assertEqual(detail.data["articles"], [self.independent.pk])

    def test_journalist_can_create_newsletter_with_approved_articles(self):
        response = self.api_client_for(self.journalist).post(
            reverse("newsletter-list"),
            {"title": "Digest", "description": "Best of",
             "articles": [self.independent.pk, self.publisher_article.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        newsletter = Newsletter.objects.get(pk=response.data["id"])
        self.assertEqual(newsletter.author, self.journalist)
        self.assertEqual(newsletter.articles.count(), 2)

    def test_newsletter_rejects_unapproved_articles(self):
        response = self.api_client_for(self.journalist).post(
            reverse("newsletter-list"),
            {"title": "Digest", "articles": [self.draft.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("articles", response.data)

    def test_reader_cannot_create_newsletter(self):
        response = self.api_client_for(self.reader).post(
            reverse("newsletter-list"), {"title": "Digest"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_delete_any_newsletter(self):
        newsletter = self.make_newsletter(self.journalist)
        response = self.api_client_for(self.editor).delete(
            reverse("newsletter-detail", args=[newsletter.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_journalist_cannot_edit_another_journalists_newsletter(self):
        newsletter = self.make_newsletter(self.other_journalist)
        response = self.api_client_for(self.journalist).patch(
            reverse("newsletter-detail", args=[newsletter.pk]),
            {"title": "Mine now"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_journalist_can_edit_own_newsletter(self):
        newsletter = self.make_newsletter(self.journalist)
        response = self.api_client_for(self.journalist).patch(
            reverse("newsletter-detail", args=[newsletter.pk]),
            {"title": "Renamed"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        newsletter.refresh_from_db()
        self.assertEqual(newsletter.title, "Renamed")


class PublisherApiTests(NewsTestCase):
    """Publishers are readable but not writable through the API."""

    def test_reader_can_list_publishers(self):
        response = self.api_client_for(self.reader).get(
            reverse("publisher-list")
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {item["name"] for item in response.data}
        self.assertEqual(names, {"Daily Planet", "The Gazette"})

    def test_publisher_lists_staff_ids(self):
        response = self.api_client_for(self.reader).get(
            reverse("publisher-detail", args=[self.publisher.pk])
        )
        self.assertEqual(response.data["journalists"], [self.journalist.pk])
        self.assertEqual(response.data["editors"], [self.editor.pk])

    def test_publishers_cannot_be_created_through_api(self):
        response = self.api_client_for(self.editor).post(
            reverse("publisher-list"), {"name": "New"}, format="json"
        )
        self.assertEqual(response.status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)


class ApprovedEndpointTests(NewsTestCase):
    """POST /api/approved/ logs approved articles (internal use)."""

    def payload(self):
        """A valid body, as built by the signal."""
        return {
            "article_id": self.independent.pk,
            "title": "Independent scoop",
            "content": "Body",
            "author": "jane",
            "publisher": None,
            "approved_by": "editor",
            "created_at": "2026-10-12T20:00:00+01:00",
        }

    def test_valid_post_with_token_is_logged(self):
        response = APIClient().post(
            reverse("api-approved"), self.payload(), format="json",
            HTTP_X_INTERNAL_TOKEN=settings.APPROVED_API_TOKEN,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        log = ApprovedArticleLog.objects.get()
        self.assertEqual(log.article, self.independent)
        self.assertEqual(log.payload["author"], "jane")

    def test_post_without_token_is_forbidden(self):
        response = APIClient().post(
            reverse("api-approved"), self.payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ApprovedArticleLog.objects.count(), 0)

    def test_post_with_wrong_token_is_forbidden(self):
        response = APIClient().post(
            reverse("api-approved"), self.payload(), format="json",
            HTTP_X_INTERNAL_TOKEN="guess",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_payload_is_rejected(self):
        response = APIClient().post(
            reverse("api-approved"), {"title": "Only a title"},
            format="json",
            HTTP_X_INTERNAL_TOKEN=settings.APPROVED_API_TOKEN,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ApprovedArticleLog.objects.count(), 0)

    def test_get_is_not_allowed(self):
        response = APIClient().get(
            reverse("api-approved"),
            HTTP_X_INTERNAL_TOKEN=settings.APPROVED_API_TOKEN,
        )
        self.assertEqual(response.status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)

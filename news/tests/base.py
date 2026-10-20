"""Shared fixtures for the news test-suite."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from news.models import Article, Newsletter, Publisher

User = get_user_model()
PASSWORD = "S3cure-pass-123"


class NewsTestCase(TestCase):
    """Creates one user per role plus a publisher and some articles.

    ``requests.post`` is patched for every test so that approving an
    article never makes a real network call. The mock is available as
    ``self.mock_post`` for assertions.
    """

    def setUp(self):
        patcher = patch("news.services.requests.post")
        self.mock_post = patcher.start()
        self.addCleanup(patcher.stop)

        self.publisher = Publisher.objects.create(name="Daily Planet")
        self.other_publisher = Publisher.objects.create(name="The Gazette")

        self.reader = self.make_user("reader", User.Role.READER)
        self.editor = self.make_user("editor", User.Role.EDITOR)
        self.journalist = self.make_user("jane", User.Role.JOURNALIST)
        self.other_journalist = self.make_user("joe", User.Role.JOURNALIST)

        self.publisher.journalists.add(self.journalist)
        self.publisher.editors.add(self.editor)
        self.other_publisher.journalists.add(self.other_journalist)

        # Independent article by Jane, publisher article by Jane, and an
        # article by Joe at the other publisher.
        self.independent = self.make_article(
            "Independent scoop", self.journalist, approved=True
        )
        self.publisher_article = self.make_article(
            "Planet exclusive", self.journalist, self.publisher, approved=True
        )
        self.other_article = self.make_article(
            "Gazette report", self.other_journalist, self.other_publisher,
            approved=True,
        )
        self.draft = self.make_article("Unapproved draft", self.journalist)
        self.mock_post.reset_mock()

    @staticmethod
    def make_user(username, role):
        """Create a user with the given role."""
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=PASSWORD,
            role=role,
        )

    @staticmethod
    def make_article(title, author, publisher=None, approved=False):
        """Create an article."""
        return Article.objects.create(
            title=title, content=f"{title} body text.", author=author,
            publisher=publisher, approved=approved,
        )

    @staticmethod
    def make_newsletter(author, articles=()):
        """Create a newsletter containing the given articles."""
        newsletter = Newsletter.objects.create(
            title="Weekly digest", description="The week's best.",
            author=author,
        )
        newsletter.articles.set(articles)
        return newsletter

    @staticmethod
    def api_client_for(user):
        """Return an API client authenticated with the user's token."""
        token, _created = Token.objects.get_or_create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

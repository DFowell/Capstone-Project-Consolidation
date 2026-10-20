"""Tests for models, role groups and permissions."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from news.models import Article

from .base import NewsTestCase

User = get_user_model()


def permission_codenames(group_name):
    """Return the set of permission codenames held by a group."""
    group = Group.objects.get(name=group_name)
    return set(group.permissions.values_list("codename", flat=True))


class RoleGroupTests(NewsTestCase):
    """Groups exist, hold the right permissions and track user roles."""

    def test_reader_group_is_view_only(self):
        self.assertEqual(
            permission_codenames("Reader"),
            {"view_article", "view_newsletter"},
        )

    def test_editor_group_can_view_update_delete_and_approve(self):
        codenames = permission_codenames("Editor")
        for expected in (
            "view_article", "change_article", "delete_article",
            "approve_article", "view_newsletter", "change_newsletter",
            "delete_newsletter",
        ):
            self.assertIn(expected, codenames)
        self.assertNotIn("add_article", codenames)
        for expected in ("view_publisher", "add_publisher",
                         "change_publisher", "delete_publisher"):
            self.assertIn(expected, codenames)

    def test_journalist_group_can_create_view_update_delete(self):
        codenames = permission_codenames("Journalist")
        for expected in (
            "add_article", "view_article", "change_article",
            "delete_article", "add_newsletter", "view_newsletter",
            "change_newsletter", "delete_newsletter",
        ):
            self.assertIn(expected, codenames)
        self.assertNotIn("approve_article", codenames)

    def test_user_is_placed_in_group_matching_role(self):
        self.assertEqual(
            list(self.reader.groups.values_list("name", flat=True)),
            ["Reader"],
        )
        self.assertEqual(
            list(self.journalist.groups.values_list("name", flat=True)),
            ["Journalist"],
        )

    def test_changing_role_moves_user_to_new_group(self):
        self.reader.role = User.Role.EDITOR
        self.reader.save()
        self.assertEqual(
            list(self.reader.groups.values_list("name", flat=True)),
            ["Editor"],
        )
        self.assertTrue(self.reader.has_perm("news.approve_article"))

    def test_reader_lacks_write_permissions(self):
        self.assertTrue(self.reader.has_perm("news.view_article"))
        self.assertFalse(self.reader.has_perm("news.add_article"))
        self.assertFalse(self.reader.has_perm("news.delete_article"))


class RoleSpecificFieldTests(NewsTestCase):
    """Reader and journalist fields are mutually exclusive."""

    def test_reader_can_subscribe(self):
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.subscribed_journalists.add(self.journalist)
        self.assertEqual(
            list(self.reader.publisher_subscriptions), [self.publisher]
        )
        self.assertEqual(
            list(self.reader.journalist_subscriptions), [self.journalist]
        )

    def test_reader_has_no_journalist_fields(self):
        self.assertIsNone(self.reader.independent_articles)
        self.assertIsNone(self.reader.independent_newsletters)

    def test_journalist_reader_fields_are_none(self):
        self.assertIsNone(self.journalist.publisher_subscriptions)
        self.assertIsNone(self.journalist.journalist_subscriptions)

    def test_journalist_independent_articles_exclude_publisher_work(self):
        independent = list(self.journalist.independent_articles)
        self.assertIn(self.independent, independent)
        self.assertIn(self.draft, independent)
        self.assertNotIn(self.publisher_article, independent)

    def test_journalist_independent_newsletters(self):
        newsletter = self.make_newsletter(self.journalist)
        self.assertEqual(
            list(self.journalist.independent_newsletters), [newsletter]
        )

    def test_promoting_reader_to_journalist_clears_subscriptions(self):
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.role = User.Role.JOURNALIST
        self.reader.save()
        self.assertEqual(self.reader.subscribed_publishers.count(), 0)
        self.assertIsNone(self.reader.publisher_subscriptions)

    def test_journalist_cannot_gain_subscriptions(self):
        self.journalist.subscribed_publishers.add(self.publisher)
        self.assertEqual(self.journalist.subscribed_publishers.count(), 0)

    def test_non_reader_removed_when_added_from_reverse_side(self):
        self.publisher.subscribers.add(self.reader, self.editor)
        self.assertEqual(list(self.publisher.subscribers.all()),
                         [self.reader])


class ArticleModelTests(NewsTestCase):
    """Validation rules on Article."""

    def test_article_defaults_to_unapproved(self):
        self.assertFalse(self.draft.approved)

    def test_independent_flag(self):
        self.assertTrue(self.independent.is_independent)
        self.assertFalse(self.publisher_article.is_independent)

    def test_author_must_be_journalist(self):
        article = Article(title="x", content="y", author=self.reader)
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_author_must_belong_to_chosen_publisher(self):
        article = Article(
            title="x", content="y", author=self.journalist,
            publisher=self.other_publisher,
        )
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_valid_publisher_article_passes_validation(self):
        article = Article(
            title="x", content="y", author=self.journalist,
            publisher=self.publisher,
        )
        article.full_clean()  # does not raise

    def test_publisher_can_have_multiple_editors_and_journalists(self):
        second_editor = self.make_user("editor2", User.Role.EDITOR)
        self.publisher.editors.add(second_editor)
        self.publisher.journalists.add(self.other_journalist)
        self.assertEqual(self.publisher.editors.count(), 2)
        self.assertEqual(self.publisher.journalists.count(), 2)


class NewsletterModelTests(NewsTestCase):
    """Newsletters hold many articles and belong to a journalist."""

    def test_newsletter_collects_articles(self):
        newsletter = self.make_newsletter(
            self.journalist, [self.independent, self.publisher_article]
        )
        self.assertEqual(newsletter.articles.count(), 2)
        self.assertEqual(self.independent.newsletters.first(), newsletter)


class AbsoluteUrlTests(NewsTestCase):
    """Create/update views redirect using ``get_absolute_url``."""

    def test_article_url_points_to_detail_page(self):
        self.assertEqual(
            self.independent.get_absolute_url(),
            f"/articles/{self.independent.pk}/",
        )

    def test_newsletter_url_points_to_detail_page(self):
        newsletter = self.make_newsletter(self.journalist)
        self.assertEqual(
            newsletter.get_absolute_url(), f"/newsletters/{newsletter.pk}/"
        )


class PartialSaveTests(NewsTestCase):
    """Saving only unrelated fields must not disturb the role group."""

    def test_last_login_update_keeps_group_and_subscriptions(self):
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.save(update_fields=["last_login"])
        self.assertEqual(
            list(self.reader.groups.values_list("name", flat=True)),
            ["Reader"],
        )
        self.assertEqual(self.reader.subscribed_publishers.count(), 1)

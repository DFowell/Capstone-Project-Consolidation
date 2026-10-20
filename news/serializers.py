"""Django REST framework serializers."""
from rest_framework import serializers

from .models import Article, CustomUser, Newsletter, Publisher


class UserSummarySerializer(serializers.ModelSerializer):
    """Minimal public view of a user (used when nested, e.g. as an author)."""

    class Meta:
        model = CustomUser
        fields = ["id", "username"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """Full read-only view of a user, including reader subscriptions."""

    class Meta:
        model = CustomUser
        fields = [
            "id", "username", "first_name", "last_name", "role",
            "subscribed_publishers", "subscribed_journalists",
        ]
        read_only_fields = fields


class PublisherSerializer(serializers.ModelSerializer):
    """A publisher with the ids of its editors and journalists."""

    class Meta:
        model = Publisher
        fields = ["id", "name", "description", "editors", "journalists"]
        read_only_fields = fields


class ArticleSerializer(serializers.ModelSerializer):
    """An article. The author is always the authenticated journalist."""

    author = UserSummarySerializer(read_only=True)
    publisher = serializers.PrimaryKeyRelatedField(
        queryset=Publisher.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Article
        fields = [
            "id", "title", "content", "author", "publisher",
            "created_at", "approved",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        """Check the author really works for the chosen publisher."""
        if self.instance is not None:
            author = self.instance.author
            publisher = attrs.get("publisher", self.instance.publisher)
        else:
            author = self.context["request"].user
            publisher = attrs.get("publisher")
        if publisher and not publisher.journalists.filter(
            pk=author.pk
        ).exists():
            raise serializers.ValidationError(
                {"publisher": "The author is not a journalist at this "
                              "publisher."}
            )
        return attrs


class NewsletterSerializer(serializers.ModelSerializer):
    """A newsletter. Only approved articles can be included."""

    author = UserSummarySerializer(read_only=True)
    articles = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=Article.objects.filter(approved=True),
    )

    class Meta:
        model = Newsletter
        fields = ["id", "title", "description", "author", "articles",
                  "created_at"]
        read_only_fields = ["id", "created_at"]


class ApprovedArticlePayloadSerializer(serializers.Serializer):
    """Validates the body POSTed to ``/api/approved/`` by the signal."""

    article_id = serializers.IntegerField()
    title = serializers.CharField(max_length=255)
    content = serializers.CharField()
    author = serializers.CharField()
    publisher = serializers.CharField(allow_null=True, required=False)
    approved_by = serializers.CharField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()

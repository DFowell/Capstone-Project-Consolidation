"""REST API views.

Endpoints (all under ``/api/``):
    POST   token/                    obtain an auth token
    GET    articles/                 approved articles
    GET    articles/subscribed/      approved articles a reader follows
    GET    articles/<id>/            one article
    POST   articles/                 create (journalists)
    PUT    articles/<id>/            update (editors / owner journalist)
    DELETE articles/<id>/            delete (editors / owner journalist)
    POST   approved/                 log an approved article (internal)
"""
import logging

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ApprovedArticleLog, Article, Newsletter, Publisher
from .permissions import ContentPermission, InternalTokenPermission, is_editor
from .queries import approved_articles, article_queryset, subscribed_articles
from .serializers import (
    ApprovedArticlePayloadSerializer, ArticleSerializer,
    NewsletterSerializer, PublisherSerializer, UserSerializer,
)

logger = logging.getLogger(__name__)


class ArticleViewSet(viewsets.ModelViewSet):
    """List, retrieve, create, update and delete articles."""

    serializer_class = ArticleSerializer
    permission_classes = [ContentPermission]

    def get_queryset(self):
        """Scope the queryset by action and role.

        Lists only ever contain approved articles. A single article may
        also be unapproved if the caller is an editor or its author.
        """
        user = self.request.user
        if self.action == "list":
            return approved_articles()
        if is_editor(user):
            return article_queryset()
        return article_queryset().filter(Q(approved=True) | Q(author=user))

    @action(detail=False, methods=["get"])
    def subscribed(self, request):
        """Approved articles from the caller's subscriptions."""
        serializer = self.get_serializer(
            subscribed_articles(request.user), many=True
        )
        return Response(serializer.data)

    def _check_approval_rights(self, serializer):
        """Only editors may change the ``approved`` flag."""
        if "approved" not in serializer.validated_data:
            return
        instance = serializer.instance
        current = instance.approved if instance else False
        if serializer.validated_data["approved"] != current and not is_editor(
            self.request.user
        ):
            raise PermissionDenied("Only editors can approve articles.")

    def perform_create(self, serializer):
        """Create the article as the logged-in journalist."""
        self._check_approval_rights(serializer)
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        """Update the article, recording who approved it."""
        self._check_approval_rights(serializer)
        extra = {}
        new_state = serializer.validated_data.get("approved")
        if new_state is True and not serializer.instance.approved:
            extra["approved_by"] = self.request.user
        elif new_state is False:
            extra["approved_by"] = None
        # Saving with approved=True fires the post_save signal, which
        # e-mails subscribers and POSTs to /api/approved/.
        serializer.save(**extra)


class NewsletterViewSet(viewsets.ModelViewSet):
    """List, retrieve, create, update and delete newsletters."""

    serializer_class = NewsletterSerializer
    permission_classes = [ContentPermission]
    queryset = Newsletter.objects.select_related("author")

    def perform_create(self, serializer):
        """Create the newsletter as the logged-in journalist."""
        serializer.save(author=self.request.user)


class PublisherViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list of publishers (managed in the admin site)."""

    serializer_class = PublisherSerializer
    queryset = Publisher.objects.all()


class CurrentUserView(APIView):
    """Return the authenticated user's profile."""

    def get(self, request):
        """Serialise the caller."""
        return Response(UserSerializer(request.user).data)


class ApprovedArticleView(APIView):
    """Receive and log approved articles (the target of the signal's POST).

    Protected by a shared token instead of a user login because the caller
    is our own server, not a person.
    """

    authentication_classes = []
    permission_classes = [InternalTokenPermission]

    def post(self, request):
        """Validate the payload and store a log entry."""
        serializer = ApprovedArticlePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = (
            request.data if isinstance(request.data, dict)
            else request.data.dict()
        )
        log = ApprovedArticleLog.objects.create(
            article=Article.objects.filter(pk=data["article_id"]).first(),
            title=data["title"],
            payload=payload,
        )
        logger.info("Approved article received: %s (id %s)",
                    log.title, data["article_id"])
        return Response({"logged": log.pk}, status=status.HTTP_201_CREATED)

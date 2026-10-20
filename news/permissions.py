"""Role checks shared by the web views and the REST API."""
import hmac

from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_editor(user):
    """Return True for editors (superusers count as editors)."""
    return user.is_authenticated and (user.is_superuser or user.is_editor)


def is_journalist(user):
    """Return True for journalists."""
    return user.is_authenticated and user.is_journalist


def can_manage(user, owner_id):
    """Editors may manage anything; journalists only their own content."""
    return is_editor(user) or (is_journalist(user) and user.pk == owner_id)


class ContentPermission(BasePermission):
    """Role-based access for articles and newsletters in the API.

    * Anyone authenticated can read.
    * Only journalists can create (POST).
    * Editors and journalists can update/delete; a journalist is limited to
      their own items (checked per object).
    """

    def has_permission(self, request, view):
        """Check the request method against the user's role."""
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.method == "POST":
            return is_journalist(user)
        return is_editor(user) or is_journalist(user)

    def has_object_permission(self, request, view, obj):
        """Allow reads, but restrict writes to editors and the owner."""
        if request.method in SAFE_METHODS:
            return True
        return can_manage(request.user, obj.author_id)


class InternalTokenPermission(BasePermission):
    """Allow only callers presenting the shared internal token."""

    def has_permission(self, request, view):
        """Compare the X-Internal-Token header in constant time."""
        supplied = request.headers.get("X-Internal-Token", "")
        expected = settings.APPROVED_API_TOKEN
        return hmac.compare_digest(supplied.encode(), expected.encode())

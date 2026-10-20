"""Web (HTML) views for the news application.

Access control uses Django's permission system: each role's group holds the
model permissions defined in ``news/groups.py`` and the views check them
with ``PermissionRequiredMixin``. Object-level rules (a journalist may only
change their own work) are enforced in ``get_object``.
"""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import (
    PermissionRequiredMixin, UserPassesTestMixin,
)
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView,
)

from .forms import (
    ArticleForm, NewsletterForm, PublisherForm, RegistrationForm,
    SubscriptionForm,
)
from .models import Article, Newsletter, Publisher
from .permissions import can_manage
from .queries import approved_articles, article_queryset, subscribed_articles


class OwnerOrEditorMixin:
    """Restrict update/delete to the owner (journalist) or any editor."""

    def get_object(self, queryset=None):
        """Fetch the object, refusing users who may not manage it."""
        obj = super().get_object(queryset)
        if not can_manage(self.request.user, obj.author_id):
            raise PermissionDenied("You can only change your own work.")
        return obj


class FormPageMixin:
    """Render every form through the shared ``news/form.html`` template."""

    template_name = "news/form.html"
    page_title = ""
    submit_label = "Save"

    def get_context_data(self, **kwargs):
        """Add the heading and button label for the shared template."""
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["submit_label"] = self.submit_label
        return context


class ConfirmDeleteMixin:
    """Render every delete confirmation through one template."""

    template_name = "news/confirm_delete.html"
    delete_note = ""

    def get_context_data(self, **kwargs):
        """Add an optional warning shown under the heading."""
        context = super().get_context_data(**kwargs)
        context["delete_note"] = self.delete_note
        return context


# --- Accounts --------------------------------------------------------------
class RegisterView(FormPageMixin, CreateView):
    """Sign-up page for new readers, journalists and editors."""

    form_class = RegistrationForm
    page_title = "Create your account"
    submit_label = "Sign up"
    success_url = reverse_lazy("news:article_list")

    def dispatch(self, request, *args, **kwargs):
        """Send logged-in users straight to the article list."""
        if request.user.is_authenticated:
            return redirect("news:article_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """Create the account and log the new user in."""
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, "Welcome! Your account is ready.")
        return response


class SubscriptionView(UserPassesTestMixin, FormPageMixin, UpdateView):
    """Readers choose which publishers and journalists to follow."""

    form_class = SubscriptionForm
    page_title = "Your subscriptions"
    submit_label = "Save subscriptions"
    success_url = reverse_lazy("news:subscriptions")

    def test_func(self):
        """Only readers have subscriptions."""
        user = self.request.user
        return user.is_authenticated and user.is_reader

    def get_object(self, queryset=None):
        """Always edit the logged-in user."""
        return self.request.user

    def form_valid(self, form):
        """Save and confirm."""
        messages.success(self.request, "Subscriptions updated.")
        return super().form_valid(form)


# --- Articles --------------------------------------------------------------
class ArticleListView(PermissionRequiredMixin, ListView):
    """Approved articles; readers can narrow to their subscriptions."""

    permission_required = "news.view_article"
    template_name = "news/article_list.html"
    context_object_name = "articles"
    paginate_by = 10

    def show_subscribed_only(self):
        """Return True when the reader asked for the subscribed filter."""
        return (
            self.request.GET.get("filter") == "subscribed"
            and self.request.user.is_reader
        )

    def get_queryset(self):
        """Return approved articles, optionally only subscribed ones."""
        if self.show_subscribed_only():
            return subscribed_articles(self.request.user)
        return approved_articles()

    def get_context_data(self, **kwargs):
        """Tell the template which filter is active."""
        context = super().get_context_data(**kwargs)
        context["subscribed_only"] = self.show_subscribed_only()
        return context


class MyArticlesView(PermissionRequiredMixin, ListView):
    """A journalist's own articles, including unapproved drafts."""

    permission_required = "news.add_article"
    template_name = "news/my_articles.html"
    context_object_name = "articles"

    def get_queryset(self):
        """Return only the logged-in journalist's articles."""
        return article_queryset().filter(author=self.request.user)


class ArticleDetailView(PermissionRequiredMixin, DetailView):
    """A single article. Unapproved ones are visible to staff only."""

    permission_required = "news.view_article"
    template_name = "news/article_detail.html"
    context_object_name = "article"
    queryset = article_queryset()

    def get_object(self, queryset=None):
        """Hide unapproved articles from everyone but editors/the author."""
        article = super().get_object(queryset)
        if not article.approved and not can_manage(
            self.request.user, article.author_id
        ):
            raise Http404("Article not found.")
        return article

    def get_context_data(self, **kwargs):
        """Tell the template whether to show the edit/delete buttons."""
        context = super().get_context_data(**kwargs)
        context["can_manage"] = can_manage(
            self.request.user, self.object.author_id
        )
        return context


class ArticleCreateView(PermissionRequiredMixin, FormPageMixin, CreateView):
    """Journalists write a new article (it starts unapproved)."""

    permission_required = "news.add_article"
    model = Article
    form_class = ArticleForm
    page_title = "Write an article"
    submit_label = "Submit for review"

    def get_form_kwargs(self):
        """Pass the user so the form can limit publisher choices."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        """Set the author and send the article to the review queue."""
        form.instance.author = self.request.user
        form.instance.approved = False
        messages.success(
            self.request, "Article submitted. An editor will review it."
        )
        return super().form_valid(form)


class ArticleUpdateView(OwnerOrEditorMixin, PermissionRequiredMixin,
                        FormPageMixin, UpdateView):
    """Edit an article (owner journalist or any editor)."""

    permission_required = "news.change_article"
    model = Article
    form_class = ArticleForm
    page_title = "Edit article"

    def get_form_kwargs(self):
        """Pass the user so the form can adapt to their role."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        """Save and confirm."""
        messages.success(self.request, "Article updated.")
        return super().form_valid(form)


class ArticleDeleteView(OwnerOrEditorMixin, PermissionRequiredMixin,
                        ConfirmDeleteMixin, DeleteView):
    """Delete an article (owner journalist or any editor)."""

    permission_required = "news.delete_article"
    model = Article
    success_url = reverse_lazy("news:article_list")

    def form_valid(self, form):
        """Delete and confirm."""
        messages.success(self.request, "Article deleted.")
        return super().form_valid(form)


# --- Editor review ---------------------------------------------------------
class ReviewListView(PermissionRequiredMixin, ListView):
    """The editor's queue of articles waiting for approval."""

    permission_required = "news.approve_article"
    template_name = "news/review_list.html"
    context_object_name = "articles"

    def get_queryset(self):
        """Return unapproved articles, oldest first."""
        return article_queryset().filter(approved=False).order_by("created_at")


class ApproveArticleView(PermissionRequiredMixin, View):
    """Approve one article. POST only.

    Saving ``approved=True`` fires the ``post_save`` signal in
    ``news/signals.py``, which e-mails subscribers and POSTs the article to
    ``/api/approved/``. No notification code is needed here.
    """

    permission_required = "news.approve_article"
    http_method_names = ["post"]

    def post(self, request, pk):
        """Mark the article approved (idempotent)."""
        article = get_object_or_404(Article, pk=pk)
        if article.approved:
            messages.info(request, "That article was already approved.")
        else:
            article.approved = True
            article.approved_by = request.user
            article.save()
            messages.success(
                request, f"'{article.title}' approved and subscribers "
                         "notified."
            )
        return redirect("news:review_list")


# --- Newsletters -----------------------------------------------------------
class NewsletterListView(PermissionRequiredMixin, ListView):
    """All newsletters."""

    permission_required = "news.view_newsletter"
    template_name = "news/newsletter_list.html"
    context_object_name = "newsletters"
    queryset = Newsletter.objects.select_related("author")
    paginate_by = 10


class NewsletterDetailView(PermissionRequiredMixin, DetailView):
    """A newsletter and the articles it contains."""

    permission_required = "news.view_newsletter"
    template_name = "news/newsletter_detail.html"
    context_object_name = "newsletter"
    queryset = Newsletter.objects.select_related("author")

    def get_context_data(self, **kwargs):
        """Add the approved articles and the edit/delete button flag."""
        context = super().get_context_data(**kwargs)
        context["articles"] = self.object.articles.filter(
            approved=True
        ).select_related("author", "publisher")
        context["can_manage"] = can_manage(
            self.request.user, self.object.author_id
        )
        return context


class NewsletterCreateView(PermissionRequiredMixin, FormPageMixin,
                           CreateView):
    """Journalists curate a new newsletter."""

    permission_required = "news.add_newsletter"
    model = Newsletter
    form_class = NewsletterForm
    page_title = "Create a newsletter"

    def form_valid(self, form):
        """Set the author and confirm."""
        form.instance.author = self.request.user
        messages.success(self.request, "Newsletter created.")
        return super().form_valid(form)


class NewsletterUpdateView(OwnerOrEditorMixin, PermissionRequiredMixin,
                           FormPageMixin, UpdateView):
    """Edit a newsletter (owner journalist or any editor)."""

    permission_required = "news.change_newsletter"
    model = Newsletter
    form_class = NewsletterForm
    page_title = "Edit newsletter"

    def form_valid(self, form):
        """Save and confirm."""
        messages.success(self.request, "Newsletter updated.")
        return super().form_valid(form)


class NewsletterDeleteView(OwnerOrEditorMixin, PermissionRequiredMixin,
                           ConfirmDeleteMixin, DeleteView):
    """Delete a newsletter (owner journalist or any editor)."""

    permission_required = "news.delete_newsletter"
    model = Newsletter
    success_url = reverse_lazy("news:newsletter_list")

    def form_valid(self, form):
        """Delete and confirm."""
        messages.success(self.request, "Newsletter deleted.")
        return super().form_valid(form)


# --- Publishers (managed by editors) ----------------------------------------
class PublisherEditorMixin:
    """Only editors of a publisher (or superusers) may change it."""

    def get_object(self, queryset=None):
        """Fetch the publisher, refusing editors who do not belong to it."""
        publisher = super().get_object(queryset)
        user = self.request.user
        if not (
            user.is_superuser
            or publisher.editors.filter(pk=user.pk).exists()
        ):
            raise PermissionDenied(
                "Only an editor of this publisher can change it."
            )
        return publisher


class PublisherListView(PermissionRequiredMixin, ListView):
    """All publishers with their editors and journalists."""

    permission_required = "news.view_publisher"
    template_name = "news/publisher_list.html"
    context_object_name = "publishers"
    queryset = Publisher.objects.prefetch_related("editors", "journalists")

    def get_context_data(self, **kwargs):
        """Tell the template which publishers the user may change."""
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_superuser:
            managed = {p.pk for p in context["publishers"]}
        else:
            managed = set(user.edited_publishers.values_list("pk", flat=True))
        context["managed_ids"] = managed
        return context


class PublisherCreateView(PermissionRequiredMixin, FormPageMixin,
                          CreateView):
    """An editor creates a publisher and becomes one of its editors."""

    permission_required = "news.add_publisher"
    model = Publisher
    form_class = PublisherForm
    page_title = "Create a publisher"
    submit_label = "Create publisher"
    success_url = reverse_lazy("news:publisher_list")

    def form_valid(self, form):
        """Save, make the creator an editor of it, and confirm."""
        response = super().form_valid(form)
        if self.request.user.is_editor:
            self.object.editors.add(self.request.user)
        messages.success(self.request, "Publisher created.")
        return response


class PublisherUpdateView(PublisherEditorMixin, PermissionRequiredMixin,
                          FormPageMixin, UpdateView):
    """Edit a publisher's details, editors and journalists."""

    permission_required = "news.change_publisher"
    model = Publisher
    form_class = PublisherForm
    page_title = "Edit publisher"
    success_url = reverse_lazy("news:publisher_list")

    def form_valid(self, form):
        """Save and confirm."""
        messages.success(self.request, "Publisher updated.")
        return super().form_valid(form)


class PublisherDeleteView(PublisherEditorMixin, PermissionRequiredMixin,
                          ConfirmDeleteMixin, DeleteView):
    """Delete a publisher; its articles become independent articles."""

    permission_required = "news.delete_publisher"
    model = Publisher
    success_url = reverse_lazy("news:publisher_list")
    delete_note = (
        "Its articles are kept and become independent articles."
    )

    def form_valid(self, form):
        """Delete and confirm."""
        messages.success(self.request, "Publisher deleted.")
        return super().form_valid(form)

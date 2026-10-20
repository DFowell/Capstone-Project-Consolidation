"""URL routes for the web front end."""
from django.urls import path

from . import views

app_name = "news"

urlpatterns = [
    path("", views.ArticleListView.as_view(), name="article_list"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("subscriptions/", views.SubscriptionView.as_view(),
         name="subscriptions"),

    # Articles
    path("articles/new/", views.ArticleCreateView.as_view(),
         name="article_create"),
    path("articles/mine/", views.MyArticlesView.as_view(),
         name="my_articles"),
    path("articles/<int:pk>/", views.ArticleDetailView.as_view(),
         name="article_detail"),
    path("articles/<int:pk>/edit/", views.ArticleUpdateView.as_view(),
         name="article_update"),
    path("articles/<int:pk>/delete/", views.ArticleDeleteView.as_view(),
         name="article_delete"),

    # Editor review queue
    path("review/", views.ReviewListView.as_view(), name="review_list"),
    path("review/<int:pk>/approve/", views.ApproveArticleView.as_view(),
         name="article_approve"),

    # Publishers (editors)
    path("publishers/", views.PublisherListView.as_view(),
         name="publisher_list"),
    path("publishers/new/", views.PublisherCreateView.as_view(),
         name="publisher_create"),
    path("publishers/<int:pk>/edit/", views.PublisherUpdateView.as_view(),
         name="publisher_update"),
    path("publishers/<int:pk>/delete/", views.PublisherDeleteView.as_view(),
         name="publisher_delete"),

    # Newsletters
    path("newsletters/", views.NewsletterListView.as_view(),
         name="newsletter_list"),
    path("newsletters/new/", views.NewsletterCreateView.as_view(),
         name="newsletter_create"),
    path("newsletters/<int:pk>/", views.NewsletterDetailView.as_view(),
         name="newsletter_detail"),
    path("newsletters/<int:pk>/edit/", views.NewsletterUpdateView.as_view(),
         name="newsletter_update"),
    path("newsletters/<int:pk>/delete/", views.NewsletterDeleteView.as_view(),
         name="newsletter_delete"),
]

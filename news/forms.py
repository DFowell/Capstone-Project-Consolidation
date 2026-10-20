"""Forms used by the web front end and the admin site."""
from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Article, CustomUser, Newsletter, Publisher


class CustomUserCreationForm(UserCreationForm):
    """Admin 'add user' form bound to the custom user model."""

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "email", "role")


class CustomUserChangeForm(UserChangeForm):
    """Admin 'change user' form bound to the custom user model."""

    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = "__all__"


class RegistrationForm(CustomUserCreationForm):
    """Public sign-up form.

    Anyone can sign up as a Reader, Journalist or Editor without using
    the admin site. Staff accounts (``is_staff``/``is_superuser``) can
    still only be created from the command line or the admin site.
    """

    SELF_SERVICE_ROLES = [
        (CustomUser.Role.READER, "Reader"),
        (CustomUser.Role.JOURNALIST, "Journalist"),
        (CustomUser.Role.EDITOR, "Editor"),
    ]

    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=SELF_SERVICE_ROLES, initial=CustomUser.Role.READER
    )

    def clean_role(self):
        """Reject any role not offered, even if the POST was tampered."""
        role = self.cleaned_data["role"]
        allowed = {value for value, _label in self.SELF_SERVICE_ROLES}
        if role not in allowed:
            raise forms.ValidationError("Please choose a valid role.")
        return role


class ArticleForm(forms.ModelForm):
    """Create/edit an article.

    Journalists may attach one of their own publishers (or leave it blank
    for an independent article). Editors only edit the text, so the
    publisher field is removed for them.
    """

    class Meta:
        model = Article
        fields = ["title", "content", "publisher"]
        widgets = {"content": forms.Textarea(attrs={"rows": 10})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if user.is_journalist:
            self.fields["publisher"].queryset = user.publishers.all()
            self.fields["publisher"].required = False
            self.fields["publisher"].empty_label = "Independent (no publisher)"
            if self.instance.pk is None:
                # Needed so Article.clean() can check publisher membership.
                self.instance.author = user
        else:
            del self.fields["publisher"]


class NewsletterForm(forms.ModelForm):
    """Create/edit a newsletter from approved articles."""

    articles = forms.ModelMultipleChoiceField(
        queryset=Article.objects.filter(approved=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Newsletter
        fields = ["title", "description", "articles"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class PublisherForm(forms.ModelForm):
    """Create/edit a publisher and choose its editors and journalists."""

    editors = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.filter(role=CustomUser.Role.EDITOR),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    journalists = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.filter(role=CustomUser.Role.JOURNALIST),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Publisher
        fields = ["name", "description", "editors", "journalists"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class SubscriptionForm(forms.ModelForm):
    """Let a reader choose the publishers and journalists they follow."""

    subscribed_publishers = forms.ModelMultipleChoiceField(
        queryset=Publisher.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    subscribed_journalists = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.filter(role=CustomUser.Role.JOURNALIST),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = CustomUser
        fields = ["subscribed_publishers", "subscribed_journalists"]

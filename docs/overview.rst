Overview
========

Roles
-----

* **Reader** - can only view articles and newsletters, and subscribe to
  publishers and journalists.
* **Journalist** - can create, view, update and delete articles and
  newsletters (their own).
* **Editor** - can view, update, delete and **approve** articles and
  newsletters, and create and manage publishers.

Approval workflow
-----------------

Articles start unapproved. When an editor approves one, a ``post_save``
signal (:mod:`news.signals`) e-mails the subscribers of its journalist or
publisher and POSTs the article to the project's own ``/api/approved/``
endpoint. See :mod:`news.services` for the side effects.

REST API
--------

Authenticate with ``POST /api/token/`` and send the returned token as
``Authorization: Token <token>``. Journalists can create articles, editors
can approve them, and readers can only view. The views are in
:mod:`news.api_views`.

"""Sphinx configuration for The Newsroom documentation."""
import os
import sys

import django

# Make the project importable and start Django so autodoc can import the
# models, views and serializers.
sys.path.insert(0, os.path.abspath('..'))
# Documentation builds never talk to the database; SQLite avoids needing
# MariaDB (or the MariaDB credentials) just to build the docs.
os.environ.setdefault('DB_ENGINE', 'sqlite')
os.environ['DJANGO_SETTINGS_MODULE'] = 'news_project.settings'
django.setup()

project = 'The Newsroom'
author = 'The Newsroom developers'
release = '1.0'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
]

autodoc_member_order = 'bysource'
exclude_patterns = ['_build']
html_theme = 'alabaster'

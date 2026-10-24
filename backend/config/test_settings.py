"""
Isolated test settings for running test suite without external services.
Uses SQLite in-memory database and LocMemCache.
"""
from .settings import *

DEBUG = False

import os

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('TEST_DB_PATH', ':memory:'),
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable debug toolbar during tests
if 'debug_toolbar' in INSTALLED_APPS:
    INSTALLED_APPS.remove('debug_toolbar')

MIDDLEWARE = [m for m in MIDDLEWARE if m != 'debug_toolbar.middleware.DebugToolbarMiddleware']

# Avoid staticfiles directory warning during tests if directory does not exist
import os
if not os.path.exists(BASE_DIR / 'static'):
    STATICFILES_DIRS = []

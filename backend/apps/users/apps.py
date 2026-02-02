"""
User app configuration.
"""
from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    verbose_name = 'Users'
    
    def ready(self):
        """Import signals when app is ready."""
        try:
            import apps.users.signals  # noqa
        except ImportError:
            pass

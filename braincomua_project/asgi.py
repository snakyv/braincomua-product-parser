"""ASGI config for the parser project."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "braincomua_project.settings")
application = get_asgi_application()

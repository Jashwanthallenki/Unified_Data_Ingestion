import os

from django.core.asgi import get_asgi_application

from .env import load_env_files

load_env_files()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "breathe_esg.settings")
application = get_asgi_application()

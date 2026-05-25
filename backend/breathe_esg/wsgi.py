import os

from django.core.wsgi import get_wsgi_application

from .env import load_env_files

load_env_files()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "breathe_esg.settings")
application = get_wsgi_application()

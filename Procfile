web: cd backend && gunicorn breathe_esg.wsgi --bind 0.0.0.0:$PORT --workers 2 --log-file -
release: cd backend && python manage.py migrate --noinput && python manage.py seed_tenant && python manage.py load_lookups

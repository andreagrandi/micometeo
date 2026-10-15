web: gunicorn --chdir apps/application config.wsgi:application --workers 2 --bind 0.0.0.0:$PORT
worker: python apps/application/manage.py run_background_worker

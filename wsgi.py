"""
WSGI entry point для хостинга (Render, Heroku, PythonAnywhere, etc.)

Использование:
  gunicorn wsgi:application --bind 0.0.0.0:$PORT
  
Или для локального запуска:
  python wsgi.py
"""
import os
import sys

# Добавить текущую директорию в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from awards_refs import create_wsgi_app

application = create_wsgi_app()

# Для локального запуска
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    application.run(host="0.0.0.0", port=port, debug=False)

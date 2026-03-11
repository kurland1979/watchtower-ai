"""
WSGI Entry Point for the Dashboard API.

Gunicorn uses this file to find the Flask app.

Usage:
    gunicorn wsgi:app --bind 0.0.0.0:5000 --workers 2

Never use Flask's built-in server (app.run()) in production —
it's single-threaded and has no request queuing.
"""

from dashboard.api import app

if __name__ == "__main__":
    # Development only — production uses gunicorn
    app.run(host="0.0.0.0", port=5000)

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from dashboard.db_reader import db_reader
import os
from functools import wraps
from config.settings import settings

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")

# The hosting platform supplies PORT; use 8080 for local dashboard runs.
def dashboard_port():
    return int(os.environ.get("PORT") or os.environ.get("DASHBOARD_PORT", 8080))

# ...
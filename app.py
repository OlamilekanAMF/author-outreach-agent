"""
app.py — Single unified Flask app for Render.
Merges webhook_server.py + dashboard/routes.py into one process.
Start command: python app.py
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from config.settings import settings
from agent.deduplicator import deduplicator
from integrations.google_sheets import google_sheets
from integrations.gemini_client import gemini_client
from dashboard.db_reader import db_reader
from datetime import datetime
from functools import wraps
import logging
import os
import io
import json

from ellipticcurve.ecdsa import Ecdsa
from ellipticcurve.publicKey import PublicKey
from ellipticcurve.signature import Signature

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")

# CORS — allow all origins so Vercel frontend can connect
CORS(app, supports_credentials=False)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        from flask import make_response
        res = make_response()
        res.headers["Access-Control-Allow-Origin"]  = "*"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return res, 204

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")
DASHBOARD_TOKEN    = os.getenv("DASHBOARD_TOKEN",    "change-this-secret-token")

logger = logging.getLogger(__name__)

# Initialize DB on module load (works for both gunicorn and direct run)
from init_db import init_db
init_db()


# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth  = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        if token != DASHBOARD_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
# Auth endpoints
# ─────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def api_login():
    data     = request.get_json() or {}
    password = data.get("password", "")
    if password == DASHBOARD_PASSWORD:
        return jsonify({"token": DASHBOARD_TOKEN}), 200
    return jsonify({"error": "Invalid password"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────
# Dashboard API — read endpoints
# ─────────────────────────────────────────────

@app.route("/api/stats")
@token_required
def get_stats():
    return jsonify(db_reader.get_overview_stats())


@app.route("/api/growth")
@token_required
def get_growth():
    return jsonify(db_reader.get_weekly_growth())


@app.route("/api/daily_counts")
@token_required
def get_daily_counts():
    return jsonify(db_reader.get_daily_send_counts())


@app.route("/api/genre_performance")
@token_required
def get_genre_performance():
    return jsonify(db_reader.get_genre_performance())


@app.route("/api/status_breakdown")
@token_required
def get_status_breakdown():
    return jsonify(db_reader.get_status_breakdown())


@app.route("/api/ab_tests")
@token_required
def get_ab_tests():
    return jsonify(db_reader.get_ab_test_stats())


@app.route("/api/authors")
@token_required
def get_authors():
    page    = request.args.get("page", 1, type=int)
    status  = request.args.get("status")
    search  = request.args.get("search")
    channel = request.args.get("channel", "all")
    return jsonify(db_reader.get_authors_paginated(
        page=page, status_filter=status, search_query=search, channel=channel
    ))


@app.route("/api/author/<author_id>")
@token_required
def get_author_detail(author_id):
    author = db_reader.get_author_detail(author_id)
    if not author:
        return jsonify({"error": "Not found"}), 404
    draft = db_reader.get_email_draft(author_id)
    return jsonify({"author": author, "draft": draft})


@app.route("/api/activity")
@token_required
def get_activity():
    return jsonify(db_reader.get_activity_log())


@app.route("/api/system_logs")
@token_required
def get_system_logs():
    return jsonify(db_reader.get_system_logs())


@app.route("/api/top_leads")
@token_required
def get_top_leads():
    return jsonify(db_reader.get_top_leads())


@app.route("/api/pending_approvals")
@token_required
def get_pending_approvals():
    return jsonify(db_reader.get_pending_approvals())


# ─────────────────────────────────────────────
# Dashboard API — write endpoints
# ─────────────────────────────────────────────

@app.route("/api/approve_author", methods=["POST"])
@token_required
def approve_author():
    data      = request.get_json() or {}
    author_id = data.get("id")
    if not author_id:
        return jsonify({"error": "Missing id"}), 400

    if not db_reader.update_approval_status(author_id, "approved"):
        return jsonify({"error": "Failed to update status"}), 500

    author    = db_reader.get_author_detail(author_id)
    draft_row = db_reader.get_email_draft(author_id)

    if not author or not draft_row:
        return jsonify({"error": "Author or draft not found"}), 404

    try:
        from models import AuthorProfile, EmailDraft
        from agent.email_sender import email_sender
        from gmail_channel.gmail_sender import gmail_sender

        profile = AuthorProfile(
            id=author["id"],
            full_name=author["full_name"],
            email=author["email"],
            source_platform=author["source_platform"],
            book_titles=json.loads(author.get("book_titles", "[]")) if author.get("book_titles") else [],
            genres=json.loads(author.get("genres", "[]")) if author.get("genres") else []
        )

        draft = EmailDraft(
            author_id=author_id,
            subject=draft_row["invitation_subject"],
            plain_text_body=draft_row["invitation_body_plain"],
            html_body=draft_row["invitation_body_html"],
            email_type="invitation",
            tokens_used={},
            tone_variation=""
        )

        if author["channel"] == "main":
            res = email_sender.send_email(profile, draft)
        else:
            res = gmail_sender.send_gmail_email(profile, draft)

        if res.success:
            profile.email_status   = "sent"
            profile.email_sent     = True
            profile.approval_status = "approved"

            if author["channel"] == "main":
                from agent.deduplicator import deduplicator
                deduplicator.mark_contacted(profile)
            else:
                from gmail_channel.gmail_dedup import gmail_dedup
                gmail_dedup.mark_gmail_contacted(profile)

            return jsonify({"status": "sent"}), 200
        else:
            return jsonify({"error": res.error}), 500

    except Exception as e:
        logger.error(f"Approve failed for {author_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reject_author", methods=["POST"])
@token_required
def reject_author():
    data      = request.get_json() or {}
    author_id = data.get("id")
    if not author_id:
        return jsonify({"error": "Missing id"}), 400
    if db_reader.update_approval_status(author_id, "rejected"):
        return jsonify({"status": "rejected"}), 200
    return jsonify({"error": "Failed"}), 500


# ─────────────────────────────────────────────
# Tracking pixels & click redirects
# ─────────────────────────────────────────────

PIXEL_DATA = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
    b'\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00'
    b'\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
    b'\x44\x01\x00\x3b'
)

@app.route("/track/open")
def track_open():
    author_id = request.args.get("author_id")
    source    = request.args.get("source", "main")
    if author_id:
        if source == "gmail":
            from gmail_channel.gmail_dedup import gmail_dedup
            gmail_dedup.mark_gmail_open_detected(author_id)
            gmail_dedup.log_event("INFO", "TRACKING", f"Email opened by {author_id} (Gmail)")
            gmail_dedup.update_lead_score(author_id, 1)
        else:
            deduplicator.mark_open_detected(author_id)
            google_sheets.update_open_detected(author_id, datetime.utcnow())
            deduplicator.log_event("INFO", "TRACKING", f"Email opened by {author_id}")
            deduplicator.update_lead_score(author_id, 1)
    return send_file(io.BytesIO(PIXEL_DATA), mimetype="image/gif")


@app.route("/track/click")
def track_click():
    author_id    = request.args.get("author_id")
    source       = request.args.get("source", "main")
    redirect_url = request.args.get("url", "https://rejoicebookclub.com")
    if author_id:
        if source == "gmail":
            from gmail_channel.gmail_dedup import gmail_dedup
            gmail_dedup.log_event("INFO", "TRACKING", f"Link clicked by {author_id} (Gmail)")
            gmail_dedup.update_lead_score(author_id, 5)
        else:
            deduplicator.log_event("INFO", "TRACKING", f"Link clicked by {author_id}")
            deduplicator.update_lead_score(author_id, 5)
    return f"<html><script>window.location.href='{redirect_url}';</script></html>"


# ─────────────────────────────────────────────
# SendGrid webhooks
# ─────────────────────────────────────────────

def verify_signature(payload, signature, timestamp):
    if not settings.SENDGRID_WEBHOOK_PUBLIC_KEY:
        logger.warning("No SENDGRID_WEBHOOK_PUBLIC_KEY — skipping verification.")
        return True
    try:
        public_key    = PublicKey.fromString(settings.SENDGRID_WEBHOOK_PUBLIC_KEY)
        decoded_sig   = Signature.fromBase64(signature)
        event_payload = timestamp.encode("utf-8") + payload
        return Ecdsa.verify(event_payload.decode("utf-8"), decoded_sig, public_key)
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False


@app.route("/webhook/sendgrid-events", methods=["POST"])
def sendgrid_events():
    sig = request.headers.get("X-Twilio-Email-Event-Webhook-Signature")
    ts  = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp")
    if not verify_signature(request.data, sig, ts):
        return jsonify({"error": "Invalid signature"}), 403

    for event in request.json:
        author_id  = event.get("author_id")
        event_type = event.get("event")
        email      = event.get("email")

        if event_type == "open" and author_id:
            deduplicator.mark_open_detected(author_id)
            google_sheets.update_open_detected(author_id, datetime.utcnow())
            deduplicator.log_event("INFO", "WEBHOOK", f"Email opened by {author_id}")
            deduplicator.update_lead_score(author_id, 1)
        elif event_type == "click" and author_id:
            deduplicator.log_event("INFO", "WEBHOOK", f"Link clicked by {author_id}")
            deduplicator.update_lead_score(author_id, 5)
        elif event_type in ["bounce", "dropped"]:
            deduplicator.log_event("WARNING", "WEBHOOK", f"Email {event_type} for {email or author_id}")

    return jsonify({"status": "ok"}), 200


@app.route("/webhook/inbound", methods=["POST"])
def inbound_replies():
    data      = request.form
    sender    = data.get("from")
    text_body = data.get("text", "")
    if sender:
        email     = sender.split("<")[-1].replace(">", "").strip().lower()
        sentiment = gemini_client.classify_reply(text_body)
        deduplicator.mark_replied(email, sentiment)
        google_sheets.update_reply_detected_by_email(email)
        deduplicator.log_event("SUCCESS", "REPLY", f"Reply from {email} (Sentiment: {sentiment})")
        deduplicator.log_conversation(
            author_id=None, email=email,
            direction="incoming", subject="Re: Invitation (Webhook)", body=text_body
        )
    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────

@app.route("/")
def health():
    return jsonify({"status": "running", "service": "Author Outreach Agent"}), 200


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logging.basicConfig(level=logging.INFO)
    # Initialize database tables on startup
    from init_db import init_db
    init_db()
    app.run(host="0.0.0.0", port=port)

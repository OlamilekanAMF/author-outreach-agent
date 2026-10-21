"""
app.py — Unified Flask app for the Author Outreach Agent.
Place this in the PROJECT ROOT (same level as main.py, requirements.txt).

Render runs: gunicorn app:app
Endpoints:
  - Dashboard API  → /api/*
  - Tracking       → /track/*
  - Webhooks       → /webhook/*
  - Health check   → /
"""

import os
import json
import logging
import functools
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

# ── App setup ────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── CORS ─────────────────────────────────────────────────────
CORS(app, supports_credentials=False)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return "", 204

# ── Auth ──────────────────────────────────────────────────────
DASHBOARD_TOKEN    = os.environ.get("DASHBOARD_TOKEN",    "")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

def token_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing token"}), 401
        token = auth[len("Bearer "):]
        if token != DASHBOARD_TOKEN:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Google Sheets reader (lazy init) ─────────────────────────
_sheets_reader = None

def get_reader():
    global _sheets_reader
    if _sheets_reader is None:
        from sheets_reader import SheetsReader
        _sheets_reader = SheetsReader()
    return _sheets_reader

# ── Health check ─────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "author-outreach-agent"}), 200

@app.route("/health", methods=["GET"])
def health2():
    return jsonify({"status": "ok"}), 200

# ── Auth endpoints ────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    data     = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password:
        return jsonify({"error": "Password required"}), 400
    if password != DASHBOARD_PASSWORD:
        return jsonify({"error": "Invalid password"}), 401
    return jsonify({"token": DASHBOARD_TOKEN, "message": "Login successful"}), 200

# ── Dashboard API ─────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
@token_required
def api_stats():
    try:
        reader = get_reader()
        stats  = reader.get_overview_stats()
        growth = reader.get_weekly_growth()
        return jsonify({**stats, **growth}), 200
    except Exception as e:
        logger.error(f"/api/stats error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/growth", methods=["GET"])
@token_required
def api_growth():
    try:
        return jsonify(get_reader().get_weekly_growth()), 200
    except Exception as e:
        logger.error(f"/api/growth error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/daily_counts", methods=["GET"])
@token_required
def api_daily_counts():
    try:
        return jsonify(get_reader().get_daily_send_counts()), 200
    except Exception as e:
        logger.error(f"/api/daily_counts error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/genre_performance", methods=["GET"])
@token_required
def api_genre_performance():
    try:
        return jsonify(get_reader().get_genre_performance()), 200
    except Exception as e:
        logger.error(f"/api/genre_performance error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/status_breakdown", methods=["GET"])
@token_required
def api_status_breakdown():
    try:
        return jsonify(get_reader().get_status_breakdown()), 200
    except Exception as e:
        logger.error(f"/api/status_breakdown error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/authors", methods=["GET"])
@token_required
def api_authors():
    try:
        page     = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 25))
        status   = request.args.get("status")
        search   = request.args.get("search")
        channel  = request.args.get("channel", "all")
        result   = get_reader().get_authors_paginated(
            page=page, per_page=per_page,
            status_filter=status, search_query=search, channel=channel
        )
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"/api/authors error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/author/<author_id>", methods=["GET"])
@token_required
def api_author_detail(author_id):
    try:
        author = get_reader().get_author_detail(author_id)
        if not author:
            return jsonify({"error": "Author not found"}), 404
        return jsonify(author), 200
    except Exception as e:
        logger.error(f"/api/author/{author_id} error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/activity", methods=["GET"])
@token_required
def api_activity():
    try:
        limit = int(request.args.get("limit", 50))
        return jsonify(get_reader().get_activity_log(limit=limit)), 200
    except Exception as e:
        logger.error(f"/api/activity error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/system_logs", methods=["GET"])
@token_required
def api_system_logs():
    try:
        # Daily summaries from Sheets serve as system logs
        summaries = get_reader().get_daily_summaries(limit=50)
        logs = []
        for s in summaries:
            if s.get("errors"):
                logs.append({
                    "timestamp": s.get("date", ""),
                    "level":     "ERROR",
                    "category":  "PIPELINE",
                    "message":   str(s["errors"])[:300],
                })
            logs.append({
                "timestamp": s.get("date", ""),
                "level":     "INFO",
                "category":  "PIPELINE",
                "message":   (
                    f"Sent: {s.get('sent',0)}, "
                    f"Failed: {s.get('failed',0)}, "
                    f"Discovered: {s.get('discovered',0)}, "
                    f"Opens: {s.get('opens',0)}, "
                    f"Replies: {s.get('replies',0)}"
                ),
            })
        return jsonify(logs), 200
    except Exception as e:
        logger.error(f"/api/system_logs error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/top_leads", methods=["GET"])
@token_required
def api_top_leads():
    try:
        limit = int(request.args.get("limit", 10))
        return jsonify(get_reader().get_top_leads(limit=limit)), 200
    except Exception as e:
        logger.error(f"/api/top_leads error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ab_tests", methods=["GET"])
@token_required
def api_ab_tests():
    try:
        stats  = get_reader().get_overview_stats()
        result = [
            {
                "variant":       "Main Channel (Brevo)",
                "total_sent":    stats.get("main_sent", 0),
                "total_opens":   stats.get("main_opens", 0),
                "total_replies": stats.get("main_replies", 0),
                "open_rate":     round(
                    stats["main_opens"] / stats["main_sent"] * 100, 1
                ) if stats.get("main_sent") else 0,
            },
            {
                "variant":       "Gmail Channel",
                "total_sent":    stats.get("gmail_sent", 0),
                "total_opens":   stats.get("gmail_opens", 0),
                "total_replies": stats.get("gmail_replies", 0),
                "open_rate":     round(
                    stats["gmail_opens"] / stats["gmail_sent"] * 100, 1
                ) if stats.get("gmail_sent") else 0,
            },
        ]
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"/api/ab_tests error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/pending_approvals", methods=["GET"])
@token_required
def api_pending_approvals():
    # Approval workflow not implemented in Sheets-based flow
    return jsonify([]), 200


@app.route("/api/approve_author", methods=["POST"])
@token_required
def api_approve_author():
    data      = request.get_json(silent=True) or {}
    author_id = data.get("author_id")
    if not author_id:
        return jsonify({"error": "author_id required"}), 400
    return jsonify({"message": f"Author {author_id} approved"}), 200


@app.route("/api/reject_author", methods=["POST"])
@token_required
def api_reject_author():
    data      = request.get_json(silent=True) or {}
    author_id = data.get("author_id")
    if not author_id:
        return jsonify({"error": "author_id required"}), 400
    return jsonify({"message": f"Author {author_id} rejected"}), 200


@app.route("/api/daily_summary", methods=["GET"])
@token_required
def api_daily_summary():
    try:
        limit = int(request.args.get("limit", 30))
        return jsonify(get_reader().get_daily_summaries(limit=limit)), 200
    except Exception as e:
        logger.error(f"/api/daily_summary error: {e}")
        return jsonify({"error": str(e)}), 500


# ── Tracking ──────────────────────────────────────────────────

@app.route("/track/open", methods=["GET"])
def track_open():
    author_id = request.args.get("id", "")
    channel   = request.args.get("ch", "main")
    if author_id:
        try:
            from integrations.google_sheets import google_sheets
            from datetime import datetime as dt
            if channel == "gmail":
                google_sheets.update_gmail_open_detected(author_id, dt.utcnow())
            else:
                google_sheets.update_open_detected(author_id, dt.utcnow())
            logger.info(f"Open tracked: {author_id} ({channel})")
        except Exception as e:
            logger.error(f"Track open error: {e}")
    # Return 1x1 transparent GIF
    pixel = (
        b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
        b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00"
        b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
        b"\x44\x01\x00\x3b"
    )
    from flask import Response
    return Response(pixel, mimetype="image/gif")


@app.route("/track/click", methods=["GET"])
def track_click():
    url       = request.args.get("url", "/")
    author_id = request.args.get("id", "")
    logger.info(f"Click tracked: {author_id} → {url}")
    from flask import redirect
    return redirect(url)


# ── Webhooks ──────────────────────────────────────────────────

@app.route("/webhook/sendgrid-events", methods=["POST"])
def webhook_sendgrid():
    try:
        events = request.get_json(silent=True) or []
        for event in events:
            event_type = event.get("event", "")
            author_id  = event.get("author_id") or event.get("unique_args", {}).get("author_id", "")
            email      = event.get("email", "")
            if event_type == "open" and author_id:
                try:
                    from integrations.google_sheets import google_sheets
                    google_sheets.update_open_detected(author_id, datetime.utcnow())
                except Exception as e:
                    logger.error(f"Sendgrid open update error: {e}")
            elif event_type in ("bounce", "dropped", "spamreport"):
                logger.warning(f"Delivery issue for {email}: {event_type}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Sendgrid webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/webhook/inbound", methods=["POST"])
def webhook_inbound():
    try:
        data  = request.get_json(silent=True) or request.form.to_dict()
        email = data.get("from", data.get("sender", ""))
        if email:
            try:
                from integrations.google_sheets import google_sheets
                google_sheets.update_reply_detected_by_email(email)
                logger.info(f"Reply detected from {email}")
            except Exception as e:
                logger.error(f"Inbound reply update error: {e}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Inbound webhook error: {e}")
        return jsonify({"error": str(e)}), 500


# ── Agent trigger endpoints ───────────────────────────────────
# Called by GitHub Actions workflows via curl.
# Render has all the env vars; GitHub only needs DASHBOARD_TOKEN.

@app.route("/run/agent", methods=["POST"])
@token_required
def run_agent():
    """Trigger the main Brevo outreach pipeline in a background thread."""
    import threading
    def _run():
        try:
            logger.info("▶ Main agent pipeline started")
            from agent.orchestrator import orchestrator
            orchestrator.run_daily_pipeline()
            logger.info("✅ Main agent pipeline finished")
        except Exception as e:
            logger.error(f"Main agent pipeline error: {e}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "message": "Main agent pipeline triggered"}), 202


@app.route("/run/followup", methods=["POST"])
@token_required
def run_followup():
    """Trigger the main channel follow-up pipeline in a background thread."""
    import threading
    def _run():
        try:
            logger.info("▶ Follow-up pipeline started")
            from agent.followup_manager import followup_manager
            followup_manager.run_followup_pipeline()
            logger.info("✅ Follow-up pipeline finished")
        except Exception as e:
            logger.error(f"Follow-up pipeline error: {e}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "message": "Follow-up pipeline triggered"}), 202


@app.route("/run/gmail", methods=["POST"])
@token_required
def run_gmail():
    """Trigger the Gmail channel outreach pipeline in a background thread."""
    import threading
    def _run():
        try:
            logger.info("▶ Gmail channel pipeline started")
            from gmail_channel.gmail_orchestrator import run_gmail_pipeline
            run_gmail_pipeline()
            logger.info("✅ Gmail channel pipeline finished")
        except Exception as e:
            logger.error(f"Gmail pipeline error: {e}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "message": "Gmail channel pipeline triggered"}), 202


@app.route("/run/gmail-followup", methods=["POST"])
@token_required
def run_gmail_followup():
    """Trigger the Gmail channel follow-up pipeline in a background thread."""
    import threading
    def _run():
        try:
            logger.info("▶ Gmail follow-up pipeline started")
            from gmail_channel.gmail_followup import run_gmail_followup_pipeline
            run_gmail_followup_pipeline()
            logger.info("✅ Gmail follow-up pipeline finished")
        except Exception as e:
            logger.error(f"Gmail follow-up pipeline error: {e}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "message": "Gmail follow-up pipeline triggered"}), 202


# ── Database init (keep for backward compat, non-fatal) ──────
def _try_init_db():
    try:
        from init_db import init_db
        init_db()
    except Exception as e:
        logger.warning(f"DB init skipped (Sheets-only mode): {e}")

_try_init_db()


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

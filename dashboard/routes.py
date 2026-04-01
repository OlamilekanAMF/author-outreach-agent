from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from dashboard.db_reader import db_reader
import os
from functools import wraps
from config.settings import settings

app = Flask(__name__)
app.secret_key = os.urandom(24)

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 8080))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == DASHBOARD_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid password")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("dashboard.html")

@app.route("/api/stats")
@login_required
def get_stats():
    return jsonify(db_reader.get_overview_stats())

@app.route("/api/daily_counts")
@login_required
def get_daily_counts():
    return jsonify(db_reader.get_daily_send_counts())

@app.route("/api/status_breakdown")
@login_required
def get_status_breakdown():
    return jsonify(db_reader.get_status_breakdown())

@app.route("/api/genre_performance")
@login_required
def get_genre_performance():
    return jsonify(db_reader.get_genre_performance())

@app.route("/api/growth")
@login_required
def get_growth():
    return jsonify(db_reader.get_weekly_growth())

@app.route("/api/ab_test_stats")
@login_required
def get_ab_test_stats():
    return jsonify(db_reader.get_ab_test_stats())

@app.route("/api/authors")
@login_required
def get_authors():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status")
    search = request.args.get("search")
    channel = request.args.get("channel", "all")
    return jsonify(db_reader.get_authors_paginated(page=page, status_filter=status, search_query=search, channel=channel))

@app.route("/api/author/<author_id>")
@login_required
def get_author_detail(author_id):
    author = db_reader.get_author_detail(author_id)
    if not author:
        return jsonify({"error": "not found"}), 404
    
    draft = db_reader.get_email_draft(author_id)
    return jsonify({"author": author, "draft": draft})

@app.route("/api/activity")
@login_required
def get_activity():
    return jsonify(db_reader.get_activity_log())

@app.route("/api/system_logs")
@login_required
def get_system_logs():
    return jsonify(db_reader.get_system_logs())

@app.route("/api/top_leads")
@login_required
def get_top_leads():
    return jsonify(db_reader.get_top_leads())

@app.route("/api/pending_approvals")
@login_required
def get_pending_approvals():
    return jsonify(db_reader.get_pending_approvals())

@app.route("/api/approve_author", methods=["POST"])
@login_required
def approve_author():
    data = request.json
    author_id = data.get("id")
    if db_reader.update_approval_status(author_id, "approved"):
        # Actually send the email now
        # We need a way to trigger the send for a specific author
        from agent.email_sender import email_sender
        from gmail_channel.gmail_sender import gmail_sender
        
        author = db_reader.get_author_detail(author_id)
        draft_row = db_reader.get_email_draft(author_id)
        
        if not author or not draft_row:
            return jsonify({"error": "Author or draft not found"}), 404
            
        from models import AuthorProfile, EmailDraft
        
        import json
        profile = AuthorProfile(
            id=author['id'],
            full_name=author['full_name'],
            email=author['email'],
            source_platform=author['source_platform'],
            book_titles=json.loads(author.get('book_titles', '[]')) if author.get('book_titles') else [],
            genres=json.loads(author.get('genres', '[]')) if author.get('genres') else []
        )
        
        draft = EmailDraft(
            author_id=author_id,
            subject=draft_row['invitation_subject'],
            plain_text_body=draft_row['invitation_body_plain'],
            html_body=draft_row['invitation_body_html'],
            email_type="invitation",
            tokens_used={},
            tone_variation=""
        )
        
        if author['channel'] == 'main':
            res = email_sender.send_email(profile, draft)
        else:
            res = gmail_sender.send_gmail_email(profile, draft)
            
        if res.success:
            # Update status to 'sent' in DB
            from agent.deduplicator import deduplicator
            from gmail_channel.gmail_dedup import gmail_dedup
            
            profile.email_status = "sent"
            profile.email_sent = True
            profile.approval_status = "approved"
            
            if author['channel'] == 'main':
                deduplicator.mark_contacted(profile)
            else:
                gmail_dedup.mark_gmail_contacted(profile)
                
            return jsonify({"status": "sent"}), 200
        else:
            return jsonify({"error": res.error}), 500
            
    return jsonify({"error": "Failed to update status"}), 500

@app.route("/api/reject_author", methods=["POST"])
@login_required
def reject_author():
    data = request.json
    author_id = data.get("id")
    if db_reader.update_approval_status(author_id, "rejected"):
        return jsonify({"status": "rejected"}), 200
    return jsonify({"error": "Failed"}), 500

def start_dashboard():
    print(f"🚀 Dashboard starting at http://localhost:{DASHBOARD_PORT}")
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)

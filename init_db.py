"""
init_db.py — Creates all required SQLite tables if they don't exist.
Called automatically on startup from app.py.
"""

import sqlite3
import os
import logging
from config.settings import settings

logger = logging.getLogger(__name__)

def init_db():
    db_path = settings.DB_PATH

    # Create the data directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ── Main channel authors ──────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacted_authors (
            id TEXT PRIMARY KEY,
            full_name TEXT,
            email TEXT,
            email_source TEXT DEFAULT 'unknown',
            email_verified INTEGER DEFAULT 0,
            email_verification_result TEXT DEFAULT 'pending',
            book_titles TEXT,
            book_descriptions TEXT,
            genres TEXT,
            website_url TEXT,
            social_url TEXT,
            source_platform TEXT,
            raw_bio TEXT,
            contacted_at TEXT,
            email_sent INTEGER DEFAULT 0,
            email_sent_at TEXT,
            email_status TEXT DEFAULT 'pending',
            open_detected INTEGER DEFAULT 0,
            open_detected_at TEXT,
            replied INTEGER DEFAULT 0,
            reply_sentiment TEXT,
            followup_sent INTEGER DEFAULT 0,
            followup_sent_at TEXT,
            followup_status TEXT DEFAULT 'pending',
            ab_variant TEXT DEFAULT 'A',
            lead_score INTEGER DEFAULT 0,
            approval_status TEXT DEFAULT 'approved',
            email_subject_used TEXT
        )
    """)

    # ── Gmail channel authors ─────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gmail_contacted_authors (
            id TEXT PRIMARY KEY,
            full_name TEXT,
            email TEXT,
            email_source TEXT DEFAULT 'unknown',
            email_verified INTEGER DEFAULT 0,
            email_verification_result TEXT DEFAULT 'pending',
            book_titles TEXT,
            book_descriptions TEXT,
            genres TEXT,
            website_url TEXT,
            social_url TEXT,
            source_platform TEXT,
            raw_bio TEXT,
            contacted_at TEXT,
            email_sent INTEGER DEFAULT 0,
            email_sent_at TEXT,
            email_status TEXT DEFAULT 'pending',
            open_detected INTEGER DEFAULT 0,
            open_detected_at TEXT,
            replied INTEGER DEFAULT 0,
            reply_sentiment TEXT,
            followup_sent INTEGER DEFAULT 0,
            followup_sent_at TEXT,
            followup_status TEXT DEFAULT 'pending',
            ab_variant TEXT DEFAULT 'A',
            lead_score INTEGER DEFAULT 0,
            approval_status TEXT DEFAULT 'approved',
            email_subject_used TEXT
        )
    """)

    # ── Email drafts (main channel) ───────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id TEXT,
            invitation_subject TEXT,
            invitation_body_plain TEXT,
            invitation_body_html TEXT,
            email_type TEXT DEFAULT 'invitation',
            tone_variation TEXT,
            ab_variant TEXT DEFAULT 'A',
            tokens_used TEXT,
            word_count INTEGER DEFAULT 0,
            generated_at TEXT
        )
    """)

    # ── Email drafts (gmail channel) ──────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gmail_email_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id TEXT,
            invitation_subject TEXT,
            invitation_body_plain TEXT,
            invitation_body_html TEXT,
            email_type TEXT DEFAULT 'invitation',
            tone_variation TEXT,
            ab_variant TEXT DEFAULT 'A',
            tokens_used TEXT,
            word_count INTEGER DEFAULT 0,
            generated_at TEXT
        )
    """)

    # ── System logs ───────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level TEXT,
            category TEXT,
            message TEXT
        )
    """)

    # ── Daily summaries ───────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            discovered INTEGER DEFAULT 0,
            valid_emails INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            skipped INTEGER DEFAULT 0,
            followups_sent INTEGER DEFAULT 0,
            opens INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            sources TEXT,
            cost REAL DEFAULT 0.0,
            errors TEXT
        )
    """)

    # ── Conversations ─────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id TEXT,
            email TEXT,
            direction TEXT,
            subject TEXT,
            body TEXT,
            timestamp TEXT
        )
    """)

    conn.commit()
    conn.close()
    logger.info("✓ Database initialized successfully at %s", db_path)


if __name__ == "__main__":
    init_db()
    print("Database initialized!")

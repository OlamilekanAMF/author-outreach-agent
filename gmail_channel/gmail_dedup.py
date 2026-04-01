import sqlite3
import json
from config.settings import settings
from models import AuthorProfile, VerificationResult, EmailDraft
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class GmailDeduplicator:
    def __init__(self):
        self.db_path = settings.DB_PATH
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gmail_contacted_authors (
                id TEXT PRIMARY KEY,
                full_name TEXT,
                email TEXT UNIQUE,
                source_platform TEXT,
                contacted_at TEXT,
                email_status TEXT,
                book_titles TEXT,
                genres TEXT,
                open_detected INTEGER DEFAULT 0,
                open_detected_at TEXT,
                replied INTEGER DEFAULT 0,
                reply_sentiment TEXT,
                followup_sent INTEGER DEFAULT 0,
                followup_sent_at TEXT,
                ab_variant TEXT,
                lead_score INTEGER DEFAULT 0,
                approval_status TEXT DEFAULT 'approved'
            )
        """)
        for col in ['book_titles', 'genres']:
            try:
                cursor.execute(f"ALTER TABLE gmail_contacted_authors ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        try:
            cursor.execute("ALTER TABLE gmail_contacted_authors ADD COLUMN approval_status TEXT DEFAULT 'approved'")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE gmail_contacted_authors ADD COLUMN reply_sentiment TEXT")
        except sqlite3.OperationalError:
            pass # Column already exists
            
        try:
            cursor.execute("ALTER TABLE gmail_contacted_authors ADD COLUMN ab_variant TEXT")
            cursor.execute("ALTER TABLE gmail_contacted_authors ADD COLUMN lead_score INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gmail_email_drafts (
                email TEXT PRIMARY KEY,
                is_deliverable INTEGER,
                verified_at TEXT,
                smtp_result TEXT,
                failure_reason TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gmail_email_drafts (
                author_id TEXT PRIMARY KEY,
                invitation_subject TEXT,
                invitation_body_html TEXT,
                invitation_body_plain TEXT,
                followup_subject TEXT,
                followup_body_html TEXT,
                followup_body_plain TEXT,
                tokens_used TEXT,
                saved_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id TEXT,
                email TEXT,
                direction TEXT, -- 'outgoing', 'incoming'
                subject TEXT,
                body TEXT,
                timestamp TEXT,
                msg_id TEXT
            )
        """)
        conn.commit()
        conn.close()

    def log_gmail_conversation(self, author_id: str, email: str, direction: str, subject: str, body: str, msg_id: str = None):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (author_id, email, direction, subject, body, timestamp, msg_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (author_id, email, direction, subject, body, datetime.utcnow().isoformat(), msg_id))
        conn.commit()
        conn.close()

    def get_gmail_conversation_history(self, author_id: str = None, email: str = None):
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if author_id:
            cursor.execute("SELECT * FROM conversations WHERE author_id = ? ORDER BY timestamp ASC", (author_id,))
        else:
            cursor.execute("SELECT * FROM conversations WHERE email = ? ORDER BY timestamp ASC", (email,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def is_already_contacted_anywhere(self, email: str) -> bool:
        """
        Check main pipeline table AND Gmail table.
        An author should never receive emails from both channels.
        """
        if not email: return False
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check main table
        cursor.execute("SELECT 1 FROM contacted_authors WHERE email = ?", (email,))
        main_check = cursor.fetchone()
        
        # Check gmail table
        cursor.execute("SELECT 1 FROM gmail_contacted_authors WHERE email = ?", (email,))
        gmail_check = cursor.fetchone()
        
        conn.close()
        return bool(main_check or gmail_check)

    def is_name_contacted_anywhere(self, name: str) -> bool:
        """
        Also check by name to avoid contacting the same author
        with a different email address.
        """
        if not name: return False
        conn = self._get_connection()
        cursor = conn.cursor()
        normalized = name.strip().lower()
        
        # Check main table
        cursor.execute("SELECT 1 FROM contacted_authors WHERE LOWER(TRIM(full_name)) = ?", (normalized,))
        main_check = cursor.fetchone()
        
        # Check gmail table
        cursor.execute("SELECT 1 FROM gmail_contacted_authors WHERE LOWER(TRIM(full_name)) = ?", (normalized,))
        gmail_check = cursor.fetchone()
        
        conn.close()
        return bool(main_check or gmail_check)

    def mark_gmail_contacted(self, author: AuthorProfile):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO gmail_contacted_authors 
            (id, full_name, email, source_platform, contacted_at, email_status, ab_variant, approval_status, book_titles, genres)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (author.id, author.full_name, author.email, author.source_platform, 
              datetime.utcnow().isoformat(), author.email_status, author.ab_variant, author.approval_status,
              json.dumps(author.book_titles), json.dumps(author.genres)))
        conn.commit()
        conn.close()

    def get_gmail_cached_verification(self, email: str) -> VerificationResult | None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gmail_verification_cache WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return VerificationResult(
                email=row[0],
                is_deliverable=bool(row[1]),
                verified_at=datetime.fromisoformat(row[2]),
                smtp_result=row[3],
                failure_reason=row[4],
                syntax_valid=True,
                mx_found=True
            )
        return None

    def cache_gmail_verification(self, result: VerificationResult):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO gmail_verification_cache 
            (email, is_deliverable, verified_at, smtp_result, failure_reason)
            VALUES (?, ?, ?, ?, ?)
        """, (result.email, int(result.is_deliverable), result.verified_at.isoformat(),
              result.smtp_result, result.failure_reason))
        conn.commit()
        conn.close()

    def save_gmail_draft(self, author_id: str, draft: EmailDraft):
        conn = self._get_connection()
        cursor = conn.cursor()
        if draft.email_type == "invitation":
            cursor.execute("""
                INSERT INTO gmail_email_drafts (author_id, invitation_subject, invitation_body_html, invitation_body_plain, tokens_used, saved_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(author_id) DO UPDATE SET
                invitation_subject=excluded.invitation_subject,
                invitation_body_html=excluded.invitation_body_html,
                invitation_body_plain=excluded.invitation_body_plain,
                tokens_used=excluded.tokens_used,
                saved_at=excluded.saved_at
            """, (author_id, draft.subject, draft.html_body, draft.plain_text_body, 
                  json.dumps(draft.tokens_used), datetime.utcnow().isoformat()))
        elif draft.email_type == "followup":
            cursor.execute("""
                UPDATE gmail_email_drafts SET
                followup_subject = ?,
                followup_body_html = ?,
                followup_body_plain = ?,
                saved_at = ?
                WHERE author_id = ?
            """, (draft.subject, draft.html_body, draft.plain_text_body, 
                  datetime.utcnow().isoformat(), author_id))
        conn.commit()
        conn.close()

    def get_gmail_draft(self, author_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT invitation_subject, invitation_body_html, invitation_body_plain FROM gmail_email_drafts WHERE author_id = ?", (author_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return EmailDraft(author_id=author_id, subject=row[0], html_body=row[1], plain_text_body=row[2], 
                              email_type="invitation", tokens_used={}, tone_variation="")
        return None

    def get_gmail_followup_eligible(self) -> list[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        # Using environment variables for Gmail channel specifically if available, otherwise default
        delay_days = int(os.getenv("GMAIL_FOLLOW_UP_DELAY_DAYS", 4))
        four_days_ago = datetime.utcnow().timestamp() - (delay_days * 86400)
        cursor.execute("""
            SELECT id FROM gmail_contacted_authors 
            WHERE email_status = 'sent' AND open_detected = 1 
            AND replied = 0 AND followup_sent = 0
            AND contacted_at <= ?
        """, (datetime.fromtimestamp(four_days_ago).isoformat(),))
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ids

    def mark_gmail_open_detected(self, author_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE gmail_contacted_authors SET open_detected = 1, open_detected_at = ? WHERE id = ?", 
                       (datetime.utcnow().isoformat(), author_id))
        conn.commit()
        conn.close()

    def mark_gmail_replied(self, email: str, sentiment: str = "unknown"):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE gmail_contacted_authors SET replied = 1, reply_sentiment = ? WHERE email = ?", (sentiment, email))
        conn.commit()
        conn.close()

    def mark_gmail_followup_sent(self, author_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE gmail_contacted_authors SET followup_sent = 1, followup_sent_at = ? WHERE id = ?", 
                       (datetime.utcnow().isoformat(), author_id))
        conn.commit()
        conn.close()

    def sync_from_google_sheet_gmail_tab(self, emails: set[str]):
        # This is a stub for potential sync logic if needed
        pass

    def update_lead_score(self, author_id: str, increment: int):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE gmail_contacted_authors SET lead_score = lead_score + ? WHERE id = ?", (increment, author_id))
        conn.commit()
        conn.close()

gmail_dedup = GmailDeduplicator()

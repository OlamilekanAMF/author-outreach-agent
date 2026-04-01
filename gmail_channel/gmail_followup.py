import os
import logging
from datetime import datetime
from config.settings import settings
from gmail_channel.gmail_dedup import gmail_dedup
from gmail_channel.gmail_sender import gmail_sender
from agent.email_writer import email_writer
from integrations.google_sheets import google_sheets
from models import AuthorProfile, FollowupSummary
import time
from random import uniform

logger = logging.getLogger(__name__)

class GmailFollowupManager:
    def run_gmail_followup_pipeline(self):
        logger.info("[Gmail] Starting follow-up pipeline")
        summary = FollowupSummary(date=datetime.utcnow().strftime("%Y-%m-%d"))
        
        eligible_ids = gmail_dedup.get_gmail_followup_eligible()
        summary.eligible_authors = len(eligible_ids)
        
        for author_id in eligible_ids:
            try:
                # Need to reconstruct profile or fetch from DB
                # For brevity, assuming we have a way to fetch the full profile
                # In real code, would fetch from gmail_contacted_authors
                profile = self._fetch_profile(author_id)
                if not profile: continue
                
                draft_invitation = gmail_dedup.get_gmail_draft(author_id)
                if not draft_invitation: continue
                
                # Fetch history for smart follow-up
                history = gmail_dedup.get_gmail_conversation_history(author_id=author_id)
                if history:
                    followup_draft = email_writer.generate_smart_followup(profile, history)
                else:
                    followup_draft = email_writer.generate_followup_email(profile, draft_invitation.subject)
                
                gmail_dedup.save_gmail_draft(author_id, followup_draft)
                
                result = gmail_sender.send_gmail_email(profile, followup_draft)
                if result.success:
                    gmail_dedup.mark_gmail_followup_sent(author_id)
                    google_sheets.update_gmail_followup_status(author_id, "sent", datetime.utcnow())
                    summary.sent += 1
                else:
                    summary.failed += 1
                    summary.errors.append(f"Follow-up failed for {profile.full_name}: {result.error}")
                
                time.sleep(uniform(8.0, 15.0))
            except Exception as e:
                logger.error(f"[Gmail] Error in follow-up for {author_id}: {e}")
                summary.errors.append(str(e))
                summary.failed += 1
                
        logger.info(f"[Gmail] Follow-up complete. Sent: {summary.sent}, Failed: {summary.failed}")
        return summary

    def _fetch_profile(self, author_id: str) -> AuthorProfile | None:
        import sqlite3
        conn = sqlite3.connect(settings.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gmail_contacted_authors WHERE id = ?", (author_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return AuthorProfile(
                id=row[0],
                full_name=row[1],
                email=row[2],
                source_platform=row[3],
                email_status=row[5]
            )
        return None

gmail_followup_manager = GmailFollowupManager()

def run_gmail_followup_pipeline():
    return gmail_followup_manager.run_gmail_followup_pipeline()

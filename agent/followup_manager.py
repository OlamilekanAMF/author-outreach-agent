from config.settings import settings
from agent.deduplicator import deduplicator
from agent.email_writer import email_writer
from agent.email_sender import email_sender
from integrations.google_sheets import google_sheets
from integrations.google_docs import google_docs
from models import AuthorProfile, FollowupSummary
import logging
import time
import random
from datetime import datetime

logger = logging.getLogger(__name__)

class FollowupManager:
    def run_followup_pipeline(self) -> FollowupSummary:
        eligible_ids = deduplicator.get_followup_eligible()
        summary = FollowupSummary(
            date=datetime.utcnow().strftime("%Y-%m-%d"),
            eligible_authors=len(eligible_ids)
        )

        logger.info(f"Starting follow-up pipeline for {len(eligible_ids)} authors")

        for author_id in eligible_ids:
            try:
                # In a real app, we'd fetch the full AuthorProfile from SQLite or Sheets
                # For this implementation, we'll assume we have a way to reconstruct it
                # or we just need the basic info.
                
                # mock profile reconstruction for now (in real app, fetch from DB)
                # Let's try to get more info from DB for the prompt
                author_data = deduplicator.get_conversation_history(author_id=author_id)
                profile = AuthorProfile(id=author_id, full_name="Author") # Default
                
                # Try to get author name from contacted_authors
                import sqlite3
                conn = sqlite3.connect(settings.DB_PATH)
                row = conn.execute("SELECT full_name FROM contacted_authors WHERE id = ?", (author_id,)).fetchone()
                if row:
                    profile.full_name = row[0]
                conn.close()

                if author_data:
                    # We have history, use smart follow-up
                    followup_draft = email_writer.generate_smart_followup(profile, author_data)
                else:
                    # No history (unlikely if eligible), fallback to template
                    original_draft = deduplicator.get_email_draft(author_id)
                    subj = original_draft.subject if original_draft else "Invitation"
                    followup_draft = email_writer.generate_followup_email(profile, subj)
                
                result = email_sender.send_email(profile, followup_draft)
                if result.success:
                    deduplicator.mark_followup_sent(author_id)
                    google_sheets.update_followup_status(author_id, "sent", datetime.utcnow())
                    summary.sent += 1
                else:
                    summary.failed += 1
                
                time.sleep(random.uniform(5, 10))
            except Exception as e:
                logger.error(f"Follow-up failed for {author_id}: {e}")
                summary.errors.append(str(e))
                summary.failed += 1

        google_docs.append_followup_section(summary)
        return summary

followup_manager = FollowupManager()

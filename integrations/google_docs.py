from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from config.settings import settings
from models import AuthorProfile, DailySummary, FollowupSummary
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class GoogleDocsClient:
    def __init__(self):
        self.creds = Credentials.from_service_account_file(
            settings.GOOGLE_SERVICE_ACCOUNT_JSON,
            scopes=["https://www.googleapis.com/auth/documents"]
        )
        self.service = build("docs", "v1", credentials=self.creds)
        self.doc_id = settings.GOOGLE_DOC_ID

    def append_daily_report(self, summary: DailySummary, authors: list[AuthorProfile]):
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            text = f"\n" + "─" * 41 + "\n"
            text += f"📅 Run Date: {summary.date} | ⏰ Completed: {now} UTC\n"
            text += "─" * 41 + "\n"
            text += f"AUTHORS DISCOVERED:     {summary.discovered}\n"
            text += f"VALID EMAILS FOUND:     {summary.valid_emails}\n"
            text += f"INVITATIONS SENT:       {summary.sent}\n"
            text += f"INVITATIONS FAILED:     {summary.failed}\n"
            text += f"SKIPPED (no email):     {summary.skipped}\n"
            text += f"FOLLOW-UPS SENT:        {summary.followups_sent}\n"
            text += f"OPENS DETECTED:         {summary.opens}\n"
            text += f"REPLIES DETECTED:       {summary.replies}\n"
            text += f"SOURCES USED:           {', '.join(summary.sources)}\n"
            text += f"OPENAI COST (USD):      ${summary.cost:.4f}\n\n"

            text += "TOP 5 AUTHORS CONTACTED TODAY:\n"
            for i, author in enumerate(authors[:5], 1):
                email_masked = f"{author.email[0]}***@{author.email.split('@')[1]}" if author.email else "N/A"
                text += f"{i}. {author.full_name} — \"{author.book_titles[0] if author.book_titles else 'N/A'}\" — [{email_masked}]\n"

            if summary.errors:
                text += "\nERRORS THIS RUN:\n"
                for error in summary.errors[:5]:
                    text += f"- {error}\n"
            text += "─" * 41 + "\n"

            requests = [{
                "insertText": {
                    "location": {"index": 1},
                    "text": text
                }
            }]
            self.service.documents().batchUpdate(documentId=self.doc_id, body={"requests": requests}).execute()
        except Exception as e:
            logger.error(f"Failed to append report to Google Docs: {e}")

    def append_followup_section(self, summary: FollowupSummary):
        try:
            text = f"\n🔄 FOLLOW-UP UPDATE ({summary.date})\n"
            text += f"Eligible for follow-up: {summary.eligible_authors}\n"
            text += f"Follow-ups sent successfully: {summary.sent}\n"
            text += f"Follow-ups failed: {summary.failed}\n"
            if summary.errors:
                text += "Follow-up Errors:\n"
                for err in summary.errors[:3]:
                    text += f"- {err}\n"
            text += "─" * 41 + "\n"

            requests = [{
                "insertText": {
                    "location": {"index": 1},
                    "text": text
                }
            }]
            self.service.documents().batchUpdate(documentId=self.doc_id, body={"requests": requests}).execute()
        except Exception as e:
            logger.error(f"Failed to append follow-up section to Google Docs: {e}")

    def append_gmail_section(self, summary: DailySummary):
        try:
            text = f"\n📧 GMAIL SECONDARY CHANNEL ({summary.date})\n"
            text += f"Authors Discovered: {summary.discovered}\n"
            text += f"Invitations Sent:   {summary.sent}\n"
            text += f"Invitations Failed: {summary.failed}\n"
            text += f"Skipped:            {summary.skipped}\n"
            if summary.errors:
                text += "Errors:\n"
                for err in summary.errors[:3]:
                    text += f"- {err}\n"
            text += "─" * 41 + "\n"

            requests = [{
                "insertText": {
                    "location": {"index": 1},
                    "text": text
                }
            }]
            self.service.documents().batchUpdate(documentId=self.doc_id, body={"requests": requests}).execute()
        except Exception as e:
            logger.error(f"Failed to append gmail section to Google Docs: {e}")

google_docs = GoogleDocsClient()

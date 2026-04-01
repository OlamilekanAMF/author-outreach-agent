import gspread
from google.oauth2.service_account import Credentials
from config.settings import settings
from models import AuthorProfile, DailySummary
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

class GoogleSheetsClient:
    def __init__(self):
        self.scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self.creds = Credentials.from_service_account_file(
            settings.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=self.scope
        )
        self.client = gspread.authorize(self.creds)
        self.sheet_id = settings.GOOGLE_SHEET_ID
        self._lock = threading.Lock()

    def _get_sheet(self):
        return self.client.open_by_key(self.sheet_id)

    def append_author_row(self, author: AuthorProfile):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Authors")
                    row = [
                        author.id, author.full_name, author.email, author.email_source,
                        str(author.email_verified), author.email_verification_result,
                        ", ".join(author.book_titles[:2]), 
                        (author.book_descriptions[0][:200] if author.book_descriptions else ""),
                        ", ".join(author.genres), author.website_url, author.social_url,
                        author.source_platform, author.collected_at.isoformat(),
                        author.email_status, author.email_sent_at.isoformat() if author.email_sent_at else "",
                        "", # Subject placeholder
                        datetime.utcnow().strftime("%Y-%m-%d"),
                        str(author.open_detected), author.open_detected_at.isoformat() if author.open_detected_at else "",
                        str(author.replied), str(author.followup_sent),
                        author.followup_sent_at.isoformat() if author.followup_sent_at else "",
                        author.followup_status
                    ]
                    sheet.append_row(row)
                except Exception as e:
                    logger.error(f"Failed to append author row to Google Sheets: {e}")

        threading.Thread(target=_run).start()

    def update_author_status(self, author_id: str, status: str, sent_at: datetime):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Authors")
                    cell = sheet.find(author_id)
                    if cell:
                        sheet.update_cell(cell.row, 14, status) # O column
                        sheet.update_cell(cell.row, 15, sent_at.isoformat()) # P column
                except Exception as e:
                    logger.error(f"Failed to update author status in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def update_author_email_subject(self, author_id: str, subject: str):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Authors")
                    cell = sheet.find(author_id)
                    if cell:
                        sheet.update_cell(cell.row, 16, subject) # Q column
                except Exception as e:
                    logger.error(f"Failed to update author email subject in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def update_open_detected(self, author_id: str, detected_at: datetime):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Authors")
                    cell = sheet.find(author_id)
                    if cell:
                        sheet.update_cell(cell.row, 18, "True") # R column
                        sheet.update_cell(cell.row, 19, detected_at.isoformat()) # S column
                except Exception as e:
                    logger.error(f"Failed to update open detection in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def update_reply_detected_by_email(self, email: str):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Authors")
                    cell = sheet.find(email)
                    if cell:
                        sheet.update_cell(cell.row, 20, "True") # T column
                except Exception as e:
                    logger.error(f"Failed to update reply detection in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def write_daily_summary(self, summary: DailySummary):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Daily Summary")
                    row = [
                        summary.date, summary.discovered, summary.valid_emails,
                        summary.sent, summary.failed, summary.skipped,
                        summary.followups_sent, summary.opens, summary.replies,
                        ", ".join(summary.sources), summary.cost,
                        "; ".join(summary.errors[:5])
                    ]
                    sheet.append_row(row)
                except Exception as e:
                    logger.error(f"Failed to write daily summary to Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def get_all_seen_emails(self):
        try:
            sheet = self._get_sheet().worksheet("Authors")
            emails = sheet.col_values(3)[1:] # Column C, skip header
            return set(emails)
        except Exception as e:
            logger.error(f"Failed to get seen emails from Google Sheets: {e}")
            return set()

    # --- Gmail Channel Functions ---

    def append_gmail_author_row(self, author: AuthorProfile):
        def _run():
            with self._lock:
                try:
                    # Ensure tab exists or get it
                    try:
                        sheet = self._get_sheet().worksheet("Gmail Channel")
                    except gspread.exceptions.WorksheetNotFound:
                        # Create if not exists with headers
                        sheet = self._get_sheet().add_worksheet("Gmail Channel", rows=1000, cols=26)
                        headers = [
                            "Author ID", "Full Name", "Email", "Email Source", "Email Verified",
                            "Verification Result", "Book Title 1", "Book Description 1", "Book Title 2",
                            "Genre(s)", "Website URL", "Social URL", "Source Platform", "Date Collected",
                            "Email Status", "Date Email Sent", "Email Subject Used", "Run Date",
                            "Open Detected", "Open Detected At", "Reply Detected", "Follow-Up Sent",
                            "Follow-Up Sent At", "Follow-Up Status", "Channel"
                        ]
                        sheet.append_row(headers)
                    
                    row = [
                        author.id, author.full_name, author.email, author.email_source,
                        str(author.email_verified), author.email_verification_result,
                        ", ".join(author.book_titles[:2]), 
                        (author.book_descriptions[0][:200] if author.book_descriptions else ""),
                        "", # Title 2
                        ", ".join(author.genres), author.website_url, author.social_url,
                        author.source_platform, author.collected_at.isoformat(),
                        author.email_status, author.email_sent_at.isoformat() if author.email_sent_at else "",
                        "", # Subject
                        datetime.utcnow().strftime("%Y-%m-%d"),
                        str(author.open_detected), author.open_detected_at.isoformat() if author.open_detected_at else "",
                        str(author.replied), str(author.followup_sent),
                        author.followup_sent_at.isoformat() if author.followup_sent_at else "",
                        author.followup_status, "gmail"
                    ]
                    sheet.append_row(row)
                except Exception as e:
                    logger.error(f"Failed to append gmail author row to Google Sheets: {e}")

        threading.Thread(target=_run).start()

    def update_gmail_author_status(self, author_id: str, status: str, sent_at: datetime):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Gmail Channel")
                    cell = sheet.find(author_id)
                    if cell:
                        sheet.update_cell(cell.row, 15, status) # O column
                        sheet.update_cell(cell.row, 16, sent_at.isoformat()) # P column
                except Exception as e:
                    logger.error(f"Failed to update gmail author status in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def update_gmail_open_detected(self, author_id: str, detected_at: datetime):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Gmail Channel")
                    cell = sheet.find(author_id)
                    if cell:
                        sheet.update_cell(cell.row, 19, "True") # S column
                        sheet.update_cell(cell.row, 20, detected_at.isoformat()) # T column
                except Exception as e:
                    logger.error(f"Failed to update gmail open detection in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def update_gmail_reply_detected(self, author_id: str):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Gmail Channel")
                    cell = sheet.find(author_id)
                    if cell:
                        sheet.update_cell(cell.row, 21, "True") # U column
                except Exception as e:
                    logger.error(f"Failed to update gmail reply detection in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def update_gmail_reply_detected_by_email(self, email: str):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Gmail Channel")
                    cell = sheet.find(email)
                    if cell:
                        sheet.update_cell(cell.row, 21, "True") # U column
                except Exception as e:
                    logger.error(f"Failed to update gmail reply detection in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def update_gmail_followup_status(self, author_id: str, status: str, sent_at: datetime):
        def _run():
            with self._lock:
                try:
                    sheet = self._get_sheet().worksheet("Gmail Channel")
                    cell = sheet.find(author_id)
                    if cell:
                        sheet.update_cell(cell.row, 22, "True") # V column
                        sheet.update_cell(cell.row, 23, sent_at.isoformat()) # W column
                        sheet.update_cell(cell.row, 24, status) # X column
                except Exception as e:
                    logger.error(f"Failed to update gmail followup status in Google Sheets: {e}")
        threading.Thread(target=_run).start()

    def get_all_gmail_seen_emails(self) -> set[str]:
        try:
            sheet = self._get_sheet().worksheet("Gmail Channel")
            emails = sheet.col_values(3)[1:] # Column C
            return set(emails)
        except Exception:
            return set()

google_sheets = GoogleSheetsClient()

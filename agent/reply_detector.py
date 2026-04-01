import imaplib
import email
from email.header import decode_header
import os
import logging
from datetime import datetime, timedelta
from agent.deduplicator import deduplicator
from gmail_channel.gmail_dedup import gmail_dedup
from integrations.google_sheets import google_sheets
from integrations.gemini_client import gemini_client

logger = logging.getLogger(__name__)

class ReplyDetector:
    def __init__(self):
        self.server = os.getenv("IMAP_SERVER", "imap.gmail.com")
        self.port = int(os.getenv("IMAP_PORT", 993))
        self.user = os.getenv("IMAP_USER")
        self.password = os.getenv("IMAP_PASSWORD")
        self.check_days = int(os.getenv("REPLY_CHECK_DAYS", 7))

    def _get_email_body(self, msg) -> str:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                try:
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        body = part.get_payload(decode=True).decode()
                        break
                except:
                    pass
        else:
            try:
                body = msg.get_payload(decode=True).decode()
            except:
                pass
        return body

    def detect_replies(self):
        if not all([self.user, self.password]):
            logger.error("IMAP credentials missing. Skipping reply detection.")
            return

        try:
            # Connect to the server
            mail = imaplib.IMAP4_SSL(self.server, self.port)
            mail.login(self.user, self.password)
            mail.select("inbox")

            # Calculate date for search
            date = (datetime.now() - timedelta(days=self.check_days)).strftime("%d-%b-%Y")
            
            # Search for all emails from authors
            # Note: We search for ALL emails since we want to catch any incoming message from a lead
            status, messages = mail.search(None, f'(SINCE "{date}")')
            
            if status != "OK":
                logger.error("Failed to search inbox.")
                return

            email_ids = messages[0].split()
            logger.info(f"Checking {len(email_ids)} recent emails for replies...")

            for e_id in email_ids:
                status, data = mail.fetch(e_id, "(RFC822)")
                if status != "OK": continue

                msg = email.message_from_bytes(data[0][1])
                
                # Get sender email
                from_ = msg.get("From")
                if not from_: continue
                
                # Extract clean email address
                author_email = None
                if "<" in from_:
                    author_email = from_.split("<")[1].split(">")[0].strip().lower()
                else:
                    author_email = from_.strip().lower()

                if not author_email: continue

                email_body = self._get_email_body(msg)

                # Check if this sender is one of our authors
                self._process_reply(author_email, email_body)

            mail.logout()
            logger.info("Reply detection complete.")

        except Exception as e:
            logger.error(f"Reply detection error: {e}")

    def _process_reply(self, author_email: str, email_body: str):
        # 1. Check Main Channel
        if deduplicator.is_already_contacted(author_email):
            logger.info(f"🎯 Reply detected from main channel author: {author_email}")
            sentiment = gemini_client.classify_reply(email_body)
            logger.info(f"Sentiment classified as: {sentiment}")
            deduplicator.mark_replied(author_email, sentiment)
            google_sheets.update_reply_detected_by_email(author_email)
            deduplicator.log_event("SUCCESS", "REPLY", f"Reply from main channel author: {author_email} (Sentiment: {sentiment})")
            
            # Log to conversations
            deduplicator.log_conversation(
                author_id=None, # We'd need to fetch this
                email=author_email,
                direction="incoming",
                subject="Re: Invitation", # Simplified
                body=email_body
            )

        # 2. Check Gmail Channel
        if gmail_dedup.is_already_contacted_anywhere(author_email):
            logger.info(f"🎯 Reply detected from Gmail channel author: {author_email}")
            sentiment = gemini_client.classify_reply(email_body)
            logger.info(f"Sentiment classified as: {sentiment}")
            gmail_dedup.mark_gmail_replied(author_email, sentiment)
            google_sheets.update_gmail_reply_detected_by_email(author_email)
            gmail_dedup.log_event("SUCCESS", "REPLY", f"Reply from Gmail channel author: {author_email} (Sentiment: {sentiment})")
            
            # Log to conversations
            gmail_dedup.log_gmail_conversation(
                author_id=None,
                email=author_email,
                direction="incoming",
                subject="Re: Invitation",
                body=email_body
            )

reply_detector = ReplyDetector()

def detect_replies():
    reply_detector.detect_replies()

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from uuid import uuid4
from random import uniform
import time
from datetime import datetime
from config.settings import settings
from models import AuthorProfile, EmailDraft, SendResult
import logging

logger = logging.getLogger(__name__)

class GmailSender:
    def __init__(self):
        self.sender_address = os.getenv("GMAIL_SENDER_ADDRESS")
        self.app_password = os.getenv("GMAIL_APP_PASSWORD")
        self.sender_name = os.getenv("GMAIL_SENDER_NAME", "Lydia Ravenscroft")
        self.dry_run = os.getenv("GMAIL_DRY_RUN", "false").lower() == "true"

    def send_gmail_email(self, author: AuthorProfile, draft: EmailDraft) -> SendResult:
        if self.dry_run:
            logger.info(f"GMAIL DRY RUN: Would send '{draft.subject}' to {author.email}")
            return SendResult(success=True, status="dry_run", message_id=f"dry-{uuid4()}")

        if not self.sender_address or not self.app_password:
            logger.error("Gmail credentials missing from environment.")
            return SendResult(success=False, status="failed", error="missing_credentials")

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = draft.subject
            msg["From"] = f"{self.sender_name} <{self.sender_address}>"
            msg["To"] = author.email
            msg["Message-ID"] = f"<{uuid4()}@gmail.com>"
            msg["List-Unsubscribe"] = f"<mailto:{self.sender_address}>"

            # Tracking pixel with gmail source tag
            today = datetime.utcnow().strftime("%Y-%m-%d")
            tracking_url = (
                f"{settings.TRACKING_BASE_URL}/track/open"
                f"?author_id={author.id}"
                f"&run_date={today}"
                f"&source=gmail"
            )
            
            html_body = draft.html_body
            tracking_pixel = f'<img src="{tracking_url}" width="1" height="1" style="display:none;" />'
            if "</body>" in html_body:
                html_body = html_body.replace("</body>", f"{tracking_pixel}</body>")
            else:
                html_body += tracking_pixel

            msg.attach(MIMEText(draft.plain_text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Generate and attach Spotlight Card if it's an invitation
            if draft.email_type == "invitation":
                from agent.image_generator import image_generator
                from email.mime.image import MIMEImage
                book_title = author.book_titles[0] if author.book_titles else "Your Book"
                img_data = image_generator.generate_spotlight_card(author.full_name, book_title)
                if img_data:
                    img_mime = MIMEImage(img_data)
                    img_mime.add_header('Content-ID', '<spotlight_card>')
                    img_mime.add_header('Content-Disposition', 'inline', filename='spotlight.png')
                    msg.attach(img_mime)

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.ehlo()
                server.starttls()
                server.login(self.sender_address, self.app_password)
                server.sendmail(self.sender_address, author.email, msg.as_string())

            logger.info(f"[Gmail] Sent → {author.full_name} <{author.email}>")
            
            # Log to conversations
            from gmail_channel.gmail_dedup import gmail_dedup
            gmail_dedup.log_gmail_conversation(
                author_id=author.id,
                email=author.email,
                direction="outgoing",
                subject=draft.subject,
                body=draft.plain_text_body
            )
            
            return SendResult(success=True, status="sent")

        except smtplib.SMTPAuthenticationError:
            logger.critical(
                "Gmail authentication failed. "
                "Check GMAIL_APP_PASSWORD in .env — "
                "must be a 16-character App Password, not your regular Gmail password."
            )
            return SendResult(success=False, status="failed", error="gmail_auth_failed")

        except smtplib.SMTPRecipientsRefused:
            logger.error(f"[Gmail] Recipient refused: {author.email}")
            return SendResult(success=False, status="failed", error="recipient_refused")

        except Exception as e:
            logger.error(f"[Gmail] SMTP error for {author.email}: {e}")
            return SendResult(success=False, status="failed", error=str(e))

gmail_sender = GmailSender()

from config.settings import settings
from models import AuthorProfile, EmailDraft, SendResult
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import logging
import time
import random
from datetime import datetime
from agent.image_generator import image_generator

logger = logging.getLogger(__name__)

class EmailSender:
    def __init__(self):
        self.smtp_user = settings.BREVO_SMTP_USER
        self.smtp_password = settings.BREVO_SMTP_PASSWORD
        self.smtp_host = settings.BREVO_SMTP_HOST
        self.smtp_port = settings.BREVO_SMTP_PORT

    def send_email(self, author: AuthorProfile, draft: EmailDraft) -> SendResult:
        if settings.DRY_RUN:
            logger.info(f"DRY RUN: Would send '{draft.subject}' to {author.email}")
            return SendResult(True, "dry_run")

        try:
            return self._send_smtp(author, draft)
        except Exception as e:
            logger.error(f"Email sending failed for {author.email}: {e}")
            return SendResult(False, "failed", error=str(e))

    def _send_smtp(self, author: AuthorProfile, draft: EmailDraft) -> SendResult:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = draft.subject
        msg["From"] = f"{settings.SENDER_NAME} <{settings.SENDER_EMAIL}>"
        msg["To"] = author.email

        # Add tracking pixel to HTML body if base URL is provided
        html_body = draft.html_body
        if settings.TRACKING_BASE_URL:
            run_date = datetime.utcnow().strftime("%Y-%m-%d")
            pixel_url = f"{settings.TRACKING_BASE_URL}/track/open?author_id={author.id}&run_date={run_date}"
            tracking_pixel = f'<img src="{pixel_url}" width="1" height="1" style="display:none;" />'
            if "</body>" in html_body:
                html_body = html_body.replace("</body>", f"{tracking_pixel}</body>")
            else:
                html_body += tracking_pixel

        msg.attach(MIMEText(draft.plain_text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Generate and attach Spotlight Card if it's an invitation
        if draft.email_type == "invitation":
            book_title = author.book_titles[0] if author.book_titles else "Your Book"
            img_data = image_generator.generate_spotlight_card(author.full_name, book_title)
            if img_data:
                img_mime = MIMEImage(img_data)
                img_mime.add_header('Content-ID', '<spotlight_card>')
                img_mime.add_header('Content-Disposition', 'inline', filename='spotlight.png')
                msg.attach(img_mime)

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
            
            # Log to conversations
            from agent.deduplicator import deduplicator
            deduplicator.log_conversation(
                author_id=author.id,
                email=author.email,
                direction="outgoing",
                subject=draft.subject,
                body=draft.plain_text_body
            )
        
        return SendResult(True, "sent")

email_sender = EmailSender()

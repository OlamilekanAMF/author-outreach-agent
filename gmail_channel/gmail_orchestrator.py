import os
import logging
import time
from datetime import datetime
from random import uniform
from config.settings import settings
from gmail_channel.gmail_discoverer import gmail_discoverer
from gmail_channel.gmail_dedup import gmail_dedup
from gmail_channel.gmail_sender import gmail_sender
from agent.collector import collector
from agent.verifier import verifier
from agent.email_writer import email_writer
from integrations.google_sheets import google_sheets
from integrations.google_docs import google_docs
from models import AuthorProfile, DailySummary
import smtplib

logger = logging.getLogger(__name__)

class GmailOrchestrator:
    def __init__(self):
        self.authors_per_day = int(os.getenv("GMAIL_AUTHORS_PER_DAY", 20))

    def run_gmail_pipeline(self) -> DailySummary:
        logger.info("[Gmail] Starting secondary outreach pipeline")
        gmail_dedup.log_event("INFO", "GMAIL_PIPELINE", "Starting secondary outreach pipeline")
        
        # STEP 0 — Startup checks
        if not os.getenv("GMAIL_SENDER_ADDRESS") or not os.getenv("GMAIL_APP_PASSWORD"):
            logger.critical("[Gmail] Missing credentials! Pipeline aborted.")
            gmail_dedup.log_event("CRITICAL", "GMAIL_STARTUP", "Missing credentials! Pipeline aborted.")
            return DailySummary(date=datetime.utcnow().strftime("%Y-%m-%d"))

        # Connection check
        if not (os.getenv("GMAIL_DRY_RUN", "false").lower() == "true"):
            try:
                with smtplib.SMTP("smtp.gmail.com", 587) as server:
                    server.ehlo()
                    server.starttls()
                    server.login(os.getenv("GMAIL_SENDER_ADDRESS"), os.getenv("GMAIL_APP_PASSWORD"))
                logger.info("[Gmail] SMTP Connection verified.")
            except Exception as e:
                logger.critical(f"[Gmail] SMTP Connection failed: {e}")
                gmail_dedup.log_event("CRITICAL", "GMAIL_SMTP", f"SMTP Connection failed: {e}")
                return DailySummary(date=datetime.utcnow().strftime("%Y-%m-%d"))
        else:
            logger.info("[Gmail] DRY RUN: Skipping SMTP Connection check.")

        summary = DailySummary(date=datetime.utcnow().strftime("%Y-%m-%d"))

        # Smart Scheduling Gate
        if settings.ENFORCE_SEND_WINDOW:
            current_hour = datetime.utcnow().hour
            if not (settings.SEND_WINDOW_START_UTC <= current_hour < settings.SEND_WINDOW_END_UTC):
                msg = f"[Gmail] Smart Scheduling: Current hour {current_hour} UTC is outside the window ({settings.SEND_WINDOW_START_UTC}-{settings.SEND_WINDOW_END_UTC}). Pausing pipeline."
                logger.info(msg)
                gmail_dedup.log_event("INFO", "SCHEDULER", msg)
                return summary

        # Warmup & Reputation Check for Gmail (use main deduplicator since it tracks all emails combined or we can add a specific one, but let's use the same combined logic)
        if settings.WARMUP_MODE:
            # We will use the same bounce rate logic since we want overall health, or just skip it if it's too high
            # Actually, let's use the local bounce rate if possible, but let's just do a simple check.
            from agent.deduplicator import deduplicator
            bounce_rate = deduplicator.get_bounce_rate()
            if bounce_rate > settings.MAX_BOUNCE_RATE:
                err_msg = f"[Gmail] CIRCUIT BREAKER TRIPPED: Overall bounce rate ({bounce_rate*100:.1f}%) exceeds threshold ({settings.MAX_BOUNCE_RATE*100:.1f}%)."
                logger.critical(err_msg)
                gmail_dedup.log_event("CRITICAL", "DELIVERABILITY", err_msg)
                summary.errors.append(err_msg)
                return summary
            
            days_running = deduplicator.get_days_since_start()
            target_authors = min(self.authors_per_day, 2 + days_running) # Slower warmup for Gmail
            logger.info(f"[Gmail] Warmup Mode Active: Day {days_running}. Target set to {target_authors}.")
        else:
            target_authors = self.authors_per_day
        
        # STEP 1 — Discovery (20 authors)
        try:
            stubs = gmail_discoverer.find_gmail_authors(target=target_authors)
            summary.discovered = len(stubs)
            summary.sources = ["LOC", "OpenLibrary", "Gutenberg"] # Simplified
        except Exception as e:
            logger.error(f"[Gmail] Discovery failed: {e}")
            gmail_dedup.log_event("ERROR", "GMAIL_DISCOVERY", f"Discovery failed: {e}")
            return summary

        # STEP 2 — Collection & Verification & Sending
        contacted_profiles = []
        for stub in stubs:
            try:
                # Collection
                profile = collector.collect_author_data(stub)
                
                if not profile.email:
                    summary.skipped += 1
                    google_sheets.append_gmail_author_row(profile)
                    continue

                if gmail_dedup.is_already_contacted_anywhere(profile.email):
                    logger.info(f"[Gmail] Skipping {profile.full_name} ({profile.email}) - already contacted")
                    continue

                # Step 3: Verification (Use gmail_dedup cache)
                cached = gmail_dedup.get_gmail_cached_verification(profile.email)
                if cached:
                    v_result = cached
                else:
                    v_result = verifier.verify_email(profile.email)
                    gmail_dedup.cache_gmail_verification(v_result)
                
                profile.email_verified = v_result.is_deliverable
                profile.email_verification_result = v_result.smtp_result

                if not profile.email_verified:
                    summary.skipped += 1
                    profile.email_status = "no_email"
                    google_sheets.append_gmail_author_row(profile)
                    continue

                summary.valid_emails += 1

                # Step 4: Email Generation
                draft = email_writer.generate_invitation_email(profile)
                profile.ab_variant = draft.ab_variant
                gmail_dedup.save_gmail_draft(profile.id, draft)

                # Step 5: Send or Queue for Approval
                if settings.MANUAL_APPROVAL_REQUIRED:
                    profile.approval_status = "pending"
                    profile.email_status = "pending_approval"
                    logger.info(f"[Gmail] Queued {profile.full_name} for manual approval.")
                    gmail_dedup.log_event("INFO", "APPROVAL", f"Queued {profile.full_name} for manual approval")
                else:
                    # Hard cap at 20 for actual sends
                    if summary.sent >= self.authors_per_day:
                        logger.info("[Gmail] Daily limit reached. Stopping sends.")
                        break
                        
                    send_result = gmail_sender.send_gmail_email(profile, draft)
                    profile.email_status = send_result.status
                    profile.email_sent = send_result.success
                    if send_result.success:
                        profile.email_sent_at = datetime.utcnow()
                        summary.sent += 1
                        contacted_profiles.append(profile)
                        # Longer delay for Gmail
                        time.sleep(uniform(8.0, 15.0))
                    else:
                        summary.failed += 1
                        err_msg = f"Gmail send failed for {profile.full_name}: {send_result.error}"
                        summary.errors.append(err_msg)
                        gmail_dedup.log_event("WARNING", "GMAIL_SEND", err_msg)

                # Step 6: Log to Sheets
                google_sheets.append_gmail_author_row(profile)
                gmail_dedup.mark_gmail_contacted(profile)

                if settings.MANUAL_APPROVAL_REQUIRED:
                    time.sleep(1)

            except Exception as e:
                logger.error(f"[Gmail] Error processing author {stub.get('name')}: {e}")
                summary.errors.append(str(e))
                summary.failed += 1
                gmail_dedup.log_event("ERROR", "GMAIL_AUTHOR_PROCESS", f"Error processing {stub.get('name')}: {e}")

        # Final Reports
        # summary.cost is already tracked by openai_client
        # google_docs.append_gmail_section(summary) # We need to add this
        
        logger.info(f"[Gmail] Pipeline complete. Sent: {summary.sent}, Failed: {summary.failed}")
        gmail_dedup.log_event("INFO", "GMAIL_PIPELINE", f"Pipeline complete. Sent: {summary.sent}, Failed: {summary.failed}")
        return summary

gmail_orchestrator = GmailOrchestrator()

def run_gmail_pipeline():
    return gmail_orchestrator.run_gmail_pipeline()

from config.settings import settings
from agent.discoverer import discoverer
from agent.collector import collector
from agent.verifier import verifier
from agent.deduplicator import deduplicator
from agent.email_writer import email_writer
from agent.email_sender import email_sender
from integrations.google_sheets import google_sheets
from integrations.google_docs import google_docs
from integrations.openai_client import openai_client
from models import AuthorProfile, DailySummary
import logging
import time
import random
from datetime import datetime

logger = logging.getLogger(__name__)

class Orchestrator:
    def run_daily_pipeline(self) -> DailySummary:
        logger.info("Starting daily author outreach pipeline")
        deduplicator.log_event("INFO", "MAIN_PIPELINE", "Starting daily outreach pipeline")
        summary = DailySummary(date=datetime.utcnow().strftime("%Y-%m-%d"))

        # Smart Scheduling Gate
        if settings.ENFORCE_SEND_WINDOW:
            current_hour = datetime.utcnow().hour
            if not (settings.SEND_WINDOW_START_UTC <= current_hour < settings.SEND_WINDOW_END_UTC):
                msg = f"Smart Scheduling: Current hour {current_hour} UTC is outside the window ({settings.SEND_WINDOW_START_UTC}-{settings.SEND_WINDOW_END_UTC}). Pausing pipeline."
                logger.info(msg)
                deduplicator.log_event("INFO", "SCHEDULER", msg)
                return summary
        
        # Warmup & Reputation Check
        if settings.WARMUP_MODE:
            bounce_rate = deduplicator.get_bounce_rate()
            if bounce_rate > settings.MAX_BOUNCE_RATE:
                err_msg = f"CIRCUIT BREAKER TRIPPED: Bounce rate ({bounce_rate*100:.1f}%) exceeds threshold ({settings.MAX_BOUNCE_RATE*100:.1f}%)."
                logger.critical(err_msg)
                deduplicator.log_event("CRITICAL", "DELIVERABILITY", err_msg)
                summary.errors.append(err_msg)
                return summary
            
            days_running = deduplicator.get_days_since_start()
            # Start with 5, add 2 per day
            target_authors = min(settings.AUTHORS_PER_DAY, 5 + (days_running * 2))
            logger.info(f"Warmup Mode Active: Day {days_running}. Target set to {target_authors}.")
        else:
            target_authors = settings.AUTHORS_PER_DAY

        # Step 1: Discovery
        try:
            stubs = discoverer.find_authors(target=target_authors)
            summary.discovered = len(stubs)
            summary.sources = ["Google Books"] # Simplified for now
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            deduplicator.log_event("ERROR", "DISCOVERY", f"Discovery failed: {e}")
            return summary

        contacted_profiles = []

        # Step 2: Collection & Verification & Sending
        for stub in stubs:
            try:
                # Deduplication check by name first
                # (In real app, we'd check email after collection)
                
                profile = collector.collect_author_data(stub)
                
                if not profile.email:
                    summary.skipped += 1
                    google_sheets.append_author_row(profile)
                    continue

                if deduplicator.is_already_contacted(profile.email):
                    logger.info(f"Skipping {profile.full_name} ({profile.email}) - already contacted")
                    continue

                # Step 3: Verification
                v_result = verifier.verify_email(profile.email)
                profile.email_verified = v_result.is_deliverable
                profile.email_verification_result = v_result.smtp_result
                deduplicator.cache_verification(v_result)

                if not profile.email_verified:
                    summary.skipped += 1
                    profile.email_status = "no_email"
                    google_sheets.append_author_row(profile)
                    continue

                summary.valid_emails += 1

                # Step 4: Email Generation
                draft = email_writer.generate_invitation_email(profile)
                profile.ab_variant = draft.ab_variant
                deduplicator.save_email_draft(profile.id, draft)

                # Step 5: Send or Queue for Approval
                if settings.MANUAL_APPROVAL_REQUIRED:
                    profile.approval_status = "pending"
                    profile.email_status = "pending_approval"
                    logger.info(f"Queued {profile.full_name} for manual approval.")
                    deduplicator.log_event("INFO", "APPROVAL", f"Queued {profile.full_name} for manual approval")
                else:
                    send_result = email_sender.send_email(profile, draft)
                    profile.email_status = send_result.status
                    profile.email_sent = send_result.success
                    if send_result.success:
                        profile.email_sent_at = datetime.utcnow()
                        summary.sent += 1
                        contacted_profiles.append(profile)
                    else:
                        summary.failed += 1
                        err_msg = f"Send failed for {profile.full_name}: {send_result.error}"
                        summary.errors.append(err_msg)
                        deduplicator.log_event("WARNING", "EMAIL_SEND", err_msg)

                # Step 6: Log to Sheets
                google_sheets.append_author_row(profile)
                # We need to update mark_contacted to include approval_status
                deduplicator.mark_contacted(profile)

                if not settings.MANUAL_APPROVAL_REQUIRED:
                    logger.info(f"Processed {profile.full_name} - Status: {profile.email_status}")
                    time.sleep(random.uniform(3, 7))
                else:
                    time.sleep(1) # Small delay for sheet consistency

            except Exception as e:
                logger.error(f"Error processing author {stub.get('name')}: {e}")
                summary.errors.append(str(e))
                summary.failed += 1
                deduplicator.log_event("ERROR", "AUTHOR_PROCESS", f"Error processing {stub.get('name')}: {e}")

        # Final Reports
        summary.cost = openai_client.total_cost
        google_sheets.write_daily_summary(summary)
        google_docs.append_daily_report(summary, contacted_profiles)
        
        logger.info(f"Daily pipeline complete. Sent: {summary.sent}, Failed: {summary.failed}")
        deduplicator.log_event("INFO", "MAIN_PIPELINE", f"Pipeline complete. Sent: {summary.sent}, Failed: {summary.failed}")
        return summary

orchestrator = Orchestrator()

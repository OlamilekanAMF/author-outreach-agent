import smtplib
import dns.resolver
from pyisemail import is_email
from config.settings import settings
from models import VerificationResult
import logging
from datetime import datetime
import socket

logger = logging.getLogger(__name__)

class Verifier:
    def __init__(self):
        self.timeout = max(settings.EMAIL_VERIFY_TIMEOUT_SECONDS, 15) # Ensure at least 15s
        self.resolver = dns.resolver.Resolver()
        self.resolver.nameservers = ['8.8.8.8', '8.8.4.4', '1.1.1.1'] # Use reliable nameservers
        self.resolver.timeout = 5
        self.resolver.lifetime = 5

    def verify_email(self, email: str) -> VerificationResult:
        # Layer 1: Syntax
        if not is_email(email, check_dns=False):
            return VerificationResult(email, False, False, "INVALID_SYNTAX", False, failure_reason="Regex/Syntax failed")

        role_prefixes = ["admin@", "info@", "noreply@", "support@", "team@", "sales@", "marketing@", "webmaster@"]
        if any(email.lower().startswith(p) for p in role_prefixes):
            return VerificationResult(email, True, False, "ROLE_BASED", False, failure_reason="Role-based email")

        # Layer 2: MX Records
        domain = email.split("@")[1].strip().lower()
        # Clean domain (sometimes crawls pick up trailing dots/slashes)
        domain = domain.rstrip('./')
        
        try:
            records = self.resolver.resolve(domain, "MX")
            mx_records = sorted([ (r.preference, str(r.exchange).rstrip('.')) for r in records ], key=lambda x: x[0])
            mx_record = mx_records[0][1]
        except Exception as e:
            logger.warning(f"MX lookup failed for {domain}: {e}")
            return VerificationResult(email, True, False, "MX_NOT_FOUND", False, failure_reason=str(e))

        # Layer 3: SMTP Handshake
        try:
            server = smtplib.SMTP(timeout=self.timeout)
            # Increase debug level if needed: server.set_debuglevel(1)
            server.connect(mx_record)
            server.helo(socket.gethostname())
            server.mail("verify@rejoicebookclub.org")
            code, message = server.rcpt(email)
            server.quit()

            if code == 250:
                return VerificationResult(email, True, True, "DELIVERABLE", True)
            elif code == 550:
                return VerificationResult(email, True, True, "SMTP_550", False, failure_reason="User does not exist")
            else:
                return VerificationResult(email, True, True, f"SMTP_{code}", True, failure_reason=message.decode() if isinstance(message, bytes) else str(message))
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, socket.timeout, socket.error) as e:
            logger.warning(f"SMTP handshake failed/blocked for {email}: {e}")
            # If MX is valid but handshake fails (common for personal sites), we still treat as deliverable but risky
            return VerificationResult(email, True, True, "SMTP_BLOCK", True, failure_reason=str(e))
        except Exception as e:
            logger.error(f"Unexpected verification error for {email}: {e}")
            return VerificationResult(email, True, True, "VERIFY_ERROR", True, failure_reason=str(e))

verifier = Verifier()

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Settings:
    # Groq (using OpenAI SDK)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    # Gemini (for classification)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Brevo SMTP
    BREVO_SMTP_USER = os.getenv("BREVO_SMTP_USER")
    BREVO_SMTP_PASSWORD = os.getenv("BREVO_SMTP_PASSWORD")
    BREVO_SMTP_HOST = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
    BREVO_SMTP_PORT = int(os.getenv("BREVO_SMTP_PORT", 587))
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    SENDER_NAME = os.getenv("SENDER_NAME", "Lydia Ravenscroft")

    # Google
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_DOC_ID = os.getenv("GOOGLE_DOC_ID")

    # Gmail
    GMAIL_CREDENTIALS_JSON = os.getenv("GMAIL_CREDENTIALS_JSON")

    # Google Custom Search (free — 100 queries/day)
    GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
    GOOGLE_CSE_ID      = os.getenv("GOOGLE_CSE_ID", "")

    # Tracking
    TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL")

    # Agent behavior
    AUTHORS_PER_DAY = int(os.getenv("AUTHORS_PER_DAY", 50))
    FOLLOW_UP_DELAY_DAYS = int(os.getenv("FOLLOW_UP_DELAY_DAYS", 4))
    ENABLE_FOLLOW_UP = os.getenv("ENABLE_FOLLOW_UP", "true").lower() == "true"
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    EMAIL_VERIFY_TIMEOUT_SECONDS = int(os.getenv("EMAIL_VERIFY_TIMEOUT_SECONDS", 10))
    DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

    # Warmup and Deliverability
    WARMUP_MODE = os.getenv("WARMUP_MODE", "false").lower() == "true"
    MAX_BOUNCE_RATE = float(os.getenv("MAX_BOUNCE_RATE", 0.02)) # 2% bounce rate threshold

    # Smart Scheduling
    ENFORCE_SEND_WINDOW = os.getenv("ENFORCE_SEND_WINDOW", "false").lower() == "true"
    SEND_WINDOW_START_UTC = int(os.getenv("SEND_WINDOW_START_UTC", 13)) # default 9 AM EST
    SEND_WINDOW_END_UTC = int(os.getenv("SEND_WINDOW_END_UTC", 16)) # default 12 PM EST

    # Quality Control
    MANUAL_APPROVAL_REQUIRED = os.getenv("MANUAL_APPROVAL_REQUIRED", "false").lower() == "true"

    # Webhook server
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 5000))
    SENDGRID_WEBHOOK_PUBLIC_KEY = os.getenv("SENDGRID_WEBHOOK_PUBLIC_KEY", "")

    # Paths
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    DB_PATH = os.path.join(DATA_DIR, "authors.db")
    LOGS_DIR = os.path.join(DATA_DIR, "run_logs")
    FAILED_QUEUE_DIR = os.path.join(DATA_DIR, "failed_queue")
    TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

settings = Settings()

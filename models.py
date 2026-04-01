import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict

@dataclass
class AuthorProfile:
    id: str                           # UUID at collection time
    full_name: str
    email: Optional[str] = None
    email_source: str = "unknown"     # "website", "goodreads", etc.
    email_verified: bool = False
    email_verification_result: str = "pending"
    book_titles: List[str] = field(default_factory=list)
    book_descriptions: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    website_url: Optional[str] = None
    social_url: Optional[str] = None
    source_platform: str = ""
    raw_bio: Optional[str] = None
    collected_at: datetime = field(default_factory=datetime.utcnow)
    email_sent: bool = False
    email_sent_at: Optional[datetime] = None
    email_status: str = "pending"
    open_detected: bool = False
    open_detected_at: Optional[datetime] = None
    replied: bool = False
    followup_sent: bool = False
    followup_sent_at: Optional[datetime] = None
    followup_status: str = "pending"
    ab_variant: str = "A"
    lead_score: int = 0
    approval_status: str = "approved" # 'pending', 'approved', 'rejected'

@dataclass
class VerificationResult:
    email: str
    syntax_valid: bool
    mx_found: bool
    smtp_result: str
    is_deliverable: bool
    verified_at: datetime = field(default_factory=datetime.utcnow)
    failure_reason: Optional[str] = None

@dataclass
class EmailDraft:
    author_id: str
    subject: str
    plain_text_body: str
    html_body: str
    email_type: str           # "invitation" or "followup"
    tokens_used: Dict         # {token_name: filled_value}
    tone_variation: str
    ab_variant: str = "A"
    generated_at: datetime = field(default_factory=datetime.utcnow)
    word_count: int = 0

@dataclass
class SendResult:
    success: bool
    status: str               # "sent", "failed", "bounced", "spam", "dry_run"
    message_id: Optional[str] = None
    error: Optional[str] = None

@dataclass
class DailySummary:
    date: str
    discovered: int = 0
    valid_emails: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    followups_sent: int = 0
    opens: int = 0
    replies: int = 0
    sources: List[str] = field(default_factory=list)
    cost: float = 0.0
    errors: List[str] = field(default_factory=list)

@dataclass
class FollowupSummary:
    date: str
    eligible_authors: int = 0
    sent: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)

import os
import logging
from config.settings import settings
from models import AuthorProfile, EmailDraft
from integrations.openai_client import openai_client
from datetime import datetime
import random

logger = logging.getLogger(__name__)

class EmailWriter:
    def __init__(self):
        self.invitation_template_path = os.path.join(settings.TEMPLATES_DIR, "invitation_template.txt")
        self.followup_template_path = os.path.join(settings.TEMPLATES_DIR, "followup_template.txt")
        self.banned_phrases = [
            "I hope this email finds you well", "I came across your work",
            "thrilled to reach out", "exciting opportunity", "leverage", "synergy",
            "touch base", "circle back", "as per my last email", "I wanted to reach out",
            "please don't hesitate", "at your earliest convenience", "going forward",
            "hope you're doing well", "I am writing to", "I would like to",
            "Dear Author", "To Whom It May Concern", "Just following up",
            "Circling back", "Bumping this", "Wanted to check in"
        ]

    def _load_template(self, path: str) -> str:
        if not os.path.exists(path):
            logger.critical(f"Template not found: {path}")
            raise FileNotFoundError(f"Template missing: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def generate_invitation_email(self, author: AuthorProfile) -> EmailDraft:
        template = self._load_template(self.invitation_template_path)
        tone_hint = random.choice(["warm_professional", "genuinely_curious", "quietly_enthusiastic", "matter_of_fact_warm", "respectfully_admiring"])
        
        ab_variant = random.choice(["A", "B"])
        variant_instruction = "Be highly professional, concise, and direct to the point." if ab_variant == "A" else "Be extremely warm, deeply admiring, enthusiastic, and focus on building a personal connection."

        system_prompt = f"""
        You are filling in a pre-written email template on behalf of Lydia Ravenscroft, Program Director of Rejoicebookclub.
        Your ONLY job is to replace each {{{{PLACEHOLDER}}}} token with natural, specific, human-sounding text based on the author's real data.
        Rules:
        - Do NOT change any sentence structure, punctuation, or wording outside the tokens.
        - {{BOOK_INTEREST_REASON}}: a genuine 1-phrase reason tied to this specific book's actual subject matter.
        - {{BOOK_CONTEXT_DETAIL}}: pull a real detail from the book description (a date, a character, an event, or a place).
        - {{DISCUSSION_THEMES}}: 2–3 themes that genuinely match this book's content.
        - {{BOOK_QUALITY_STATEMENT}}: match the book's actual strength.
        - {{AUTHOR_JOURNEY_DETAIL}}: specific to the genre (biography, fiction, self-help).
        - {{BOOK_GENRE_LABEL}}: natural genre word (biography, novel, memoir, guide, etc.).
        - Fill tokens with a {tone_hint} quality.
        - IMPORTANT A/B TEST INSTRUCTION: {variant_instruction}
        - Return ONLY the completed email text.
        """
        
        user_prompt = f"""
        Author name: {author.full_name}
        Book title: {author.book_titles[0] if author.book_titles else 'their book'}
        Book description: {author.book_descriptions[0][:400] if author.book_descriptions else 'Not available'}
        Genre: {', '.join(author.genres[:2]) if author.genres else 'General Fiction'}
        Author bio: {author.raw_bio[:300] if author.raw_bio else 'Not available'}

        Template:
        {template}
        """
        
        res = openai_client.call_gpt(system_prompt, user_prompt)
        
        # Check for banned phrases
        for phrase in self.banned_phrases:
            if phrase.lower() in res.lower():
                res = openai_client.call_gpt(system_prompt, f"REWRITE the following email to REMOVE the banned phrase '{phrase}'. Keep everything else identical.\n\n{res}")

        # Parse Subject
        lines = res.strip().split("\n")
        subject = "Invitation to Feature Your Book"
        body_start = 0
        if lines[0].upper().startswith("SUBJECT:"):
            subject = lines[0][8:].strip()
            body_start = 1
        
        body_plain = "\n".join(lines[body_start:]).strip()
        body_html = "".join([f"<p>{p}</p>" for p in body_plain.split("\n\n") if p])

        # Add image placeholder
        body_html += '<br><div style="text-align: center;"><img src="cid:spotlight_card" alt="Author Spotlight" style="max-width: 100%; border-radius: 8px;"></div><br>'

        return EmailDraft(
            author_id=author.id,
            subject=subject,
            plain_text_body=body_plain,
            html_body=body_html,
            email_type="invitation",
            tokens_used={}, # Ideally track these
            tone_variation=tone_hint,
            ab_variant=ab_variant,
            word_count=len(body_plain.split())
        )

    def generate_smart_followup(self, author: AuthorProfile, history: list) -> EmailDraft:
        from integrations.gemini_client import gemini_client
        
        history_text = ""
        for msg in history:
            history_text += f"[{msg['direction'].upper()}] Subject: {msg['subject']}\nBody: {msg['body']}\n---\n"

        prompt = f"""
You are Lydia Ravenscroft, Program Director at Rejoicebookclub.
You are following up with an author named {author.full_name} regarding an invitation to a spotlight.

Conversation History:
{history_text}

Task:
Write a natural, low-pressure, and highly personalized follow-up email.
Rules:
- Acknowledge if they opened the email but didn't reply (if applicable).
- Reference specific details from the previous messages if it makes sense.
- Keep it under 100 words.
- Be warm and professional.
- Return ONLY the email body.

Output format:
Subject: [Your Subject Line]
[Body Text]
"""
        try:
            # We use Gemini Pro for the smart follow-up generation
            response = gemini_client.model.generate_content(prompt)
            full_text = response.text.strip()
            
            lines = full_text.split("\n")
            subject = "Following up"
            if lines[0].lower().startswith("subject:"):
                subject = lines[0].split(":", 1)[1].strip()
                body_plain = "\n".join(lines[1:]).strip()
            else:
                body_plain = full_text

            body_html = "".join([f"<p>{p}</p>" for p in body_plain.split("\n\n") if p])

            return EmailDraft(
                author_id=author.id,
                subject=subject,
                plain_text_body=body_plain,
                html_body=body_html,
                email_type="followup",
                tokens_used={},
                tone_variation="smart_followup"
            )
        except Exception as e:
            logger.error(f"Failed to generate smart follow-up: {e}")
            # Fallback to standard follow-up
            return self.generate_followup_email(author, "Re: Invitation")

    def generate_followup_email(self, author: AuthorProfile, original_subject: str) -> EmailDraft:
        template = self._load_template(self.followup_template_path)
        
        system_prompt = """
        You are filling in a short follow-up email template on behalf of Lydia Ravenscroft.
        {{AUTHOR_NAME}}: first name only.
        {{BOOK_TITLE}}: full book title.
        {{FOLLOWUP_SPECIFIC_HOOK}}: one warm, specific reason the members are still hoping to hear from this author.
        Return ONLY the completed email.
        """
        
        user_prompt = f"""
        Author name: {author.full_name}
        Book title: {author.book_titles[0] if author.book_titles else 'their book'}
        Book description: {author.book_descriptions[0][:300] if author.book_descriptions else 'Not available'}
        Original subject: {original_subject}

        Template:
        {template}
        """
        
        res = openai_client.call_gpt(system_prompt, user_prompt)
        
        lines = res.strip().split("\n")
        body_start = 0
        if lines[0].upper().startswith("SUBJECT:"):
            body_start = 1
            
        body_plain = "\n".join(lines[body_start:]).strip()
        body_html = "".join([f"<p>{p}</p>" for p in body_plain.split("\n\n") if p])

        return EmailDraft(
            author_id=author.id,
            subject=f"Re: {original_subject}",
            plain_text_body=body_plain,
            html_body=body_html,
            email_type="followup",
            tokens_used={},
            tone_variation="followup",
            word_count=len(body_plain.split())
        )

email_writer = EmailWriter()

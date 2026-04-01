import google.generativeai as genai
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.is_configured = bool(self.api_key)
        if self.is_configured:
            genai.configure(api_key=self.api_key)
            # Using gemini-pro which is generally available
            self.model = genai.GenerativeModel('gemini-pro')
        else:
            logger.warning("GEMINI_API_KEY not found. Auto-reply classification will be disabled.")

    def classify_reply(self, email_body: str) -> str:
        if not self.is_configured:
            return "unknown"
            
        prompt = f"""
You are an expert sales assistant analyzing an email reply from an author who was just invited to a book club spotlight.
Read the email body and classify their response into exactly one of the following categories. 
Return ONLY the category name, nothing else.

Categories:
- interested (They want to learn more, ask for next steps, or agree to join)
- not_interested (They politely decline or say no)
- asking_price (They ask if there is a cost or fee involved)
- wrong_person (They state they are the wrong person, agent, or publisher)
- other (Anything else, out of office, weird questions)

Email Body:
\"\"\"{email_body}\"\"\"
"""
        try:
            response = self.model.generate_content(prompt)
            result = response.text.strip().lower()
            
            # Fallback handling just in case the model is wordy
            valid_categories = ["interested", "not_interested", "asking_price", "wrong_person", "other"]
            for cat in valid_categories:
                if cat in result:
                    return cat
            return "other"
            
        except Exception as e:
            logger.error(f"Gemini API error during classification: {e}")
            return "unknown"

gemini_client = GeminiClient()

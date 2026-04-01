import openai
from tenacity import retry, wait_exponential, stop_after_attempt
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class OpenAIClient:
    def __init__(self):
        # Handle missing API key during initialization (especially for dry runs)
        api_key = settings.GROQ_API_KEY or ("dummy_key" if settings.DRY_RUN else None)
        
        # Groq is OpenAI-compatible
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        self.model = settings.GROQ_MODEL
        self.total_cost = 0.0

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(settings.MAX_RETRIES))
    def call_gpt(self, system_prompt: str, user_prompt: str, temperature: float = 0.7):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            
            # Cost estimation for Llama-3.3-70b-versatile on Groq
            # $0.59 / 1M tokens (input), $0.79 / 1M tokens (output)
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = (input_tokens * 0.59 / 1000000) + (output_tokens * 0.79 / 1000000)
            self.total_cost += cost
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            raise

openai_client = OpenAIClient()

import httpx
import re
from bs4 import BeautifulSoup
from config.settings import settings
from models import AuthorProfile
from integrations.openai_client import openai_client
import uuid
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Collector:
    def __init__(self):
        self.email_regex = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

    def collect_author_data(self, author_stub: dict) -> AuthorProfile:
        author_name = author_stub["name"]
        profile = AuthorProfile(
            id=str(uuid.uuid4()),
            full_name=author_name,
            book_titles=[author_stub.get("book_title")] if author_stub.get("book_title") else [],
            book_descriptions=[author_stub.get("description")] if author_stub.get("description") else [],
            source_platform=author_stub.get("source_platform", "Unknown"),
            collected_at=datetime.utcnow()
        )

        # Attempt to find email
        email, source = self._find_email(author_name, author_stub.get("description", ""))
        
        if not email and author_stub.get("url"):
            logger.info(f"Email not found in context for {author_name}, crawling {author_stub['url']}...")
            email, source = self._crawl_website_for_email(author_stub["url"])
            profile.website_url = author_stub["url"]

        profile.email = email
        profile.email_source = source

        return profile

    def _crawl_website_for_email(self, url: str) -> tuple[str | None, str]:
        from playwright.sync_api import sync_playwright
        from fake_useragent import UserAgent
        import tldextract
        
        ua = UserAgent()
        domain = tldextract.extract(url).registered_domain
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                # Use a realistic context
                context = browser.new_context(
                    user_agent=ua.random,
                    viewport={'width': 1280, 'height': 800}
                )
                page = context.new_page()
                
                # 1. Try to load the main page
                try:
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000) # Wait for JS to settle
                except Exception as e:
                    logger.warning(f"Initial load failed for {url}: {e}")
                    browser.close()
                    return None, "not_found"

                def extract_from_current_page():
                    content = page.content()
                    # Look for mailto links first (highest signal)
                    mailto_links = page.query_selector_all("a[href^='mailto:']")
                    for link in mailto_links:
                        href = link.get_attribute("href")
                        if href:
                            email = href.replace("mailto:", "").split("?")[0].strip()
                            if self._is_valid_author_email(email, domain):
                                return email
                    
                    # Regex fallback
                    emails = self.email_regex.findall(content)
                    valid = [e for e in emails if self._is_valid_author_email(e, domain)]
                    return valid[0] if valid else None

                # Check homepage
                email = extract_from_current_page()
                if email:
                    browser.close()
                    return email, "website_crawl_home"

                # 2. Look for Contact/About pages
                contact_selectors = [
                    "a:has-text('Contact')", "a:has-text('About')", 
                    "a:has-text('Reach')", "a:has-text('Get in touch')",
                    "a[href*='contact']", "a[href*='about']"
                ]
                
                found_subpage = False
                for selector in contact_selectors:
                    try:
                        link = page.locator(selector).first
                        if link.is_visible():
                            link.click(timeout=5000)
                            page.wait_for_timeout(3000)
                            found_subpage = True
                            break
                    except:
                        continue
                
                if found_subpage:
                    email = extract_from_current_page()
                    if email:
                        browser.close()
                        return email, "website_crawl_subpage"

                browser.close()
        except Exception as e:
            logger.error(f"Playwright crawl failed for {url}: {e}")
            
        return None, "not_found"

    def _is_valid_author_email(self, email: str, domain: str) -> bool:
        """Filters out generic support emails and ensures the email is somewhat related to the domain."""
        email = email.lower()
        banned_prefixes = ["support@", "info@", "noreply@", "webmaster@", "sales@", "service@", "admin@", "office@", "help@", "press@", "media@"]
        if any(email.startswith(p) for p in banned_prefixes):
            return False
        
        # Valid if it's a personal name or includes author keywords
        return True

    def _find_email(self, name: str, context: str) -> tuple[str | None, str]:
        # 1. Search context first
        emails = self.email_regex.findall(context)
        if emails:
            # Filter bad ones
            valid = [e for e in emails if not any(x in e.lower() for x in ["support", "info", "noreply"])]
            if valid: return valid[0], "context"

        # 2. Use GPT-4o to guess or extract from bio if available
        if context:
            prompt = f"Extract the contact email for author '{name}' from this text. Return only the email address or 'NOT_FOUND'.\n\nText: {context}"
            res = openai_client.call_gpt("You are a data extraction assistant.", prompt)
            if "@" in res:
                return res.strip(), "gpt_extraction"

        return None, "not_found"

collector = Collector()

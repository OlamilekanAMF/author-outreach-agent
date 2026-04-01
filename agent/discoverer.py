import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import random
import time
from random import uniform
from config.settings import settings
from fake_useragent import UserAgent
import logging

logger = logging.getLogger(__name__)
ua = UserAgent()

# Queries to rotate for author discovery
DUCKDUCKGO_AUTHOR_QUERIES = [
    'site:*.com "official website" author email fiction',
    'site:*.com novelist contact page 2024',
    '"biography" author contact email site',
    '"personal website" writer reach me',
    'indie author "contact" email 2024',
    'site:*.com "about the author" email',
    '"book club" author contact website',
    'award winning novelist official site email',
    'site:*.com author "contact me" book 2024',
    'debut novelist "contact" email website',
    'site:*.com "get in touch" author biography',
    'thriller author official site contact'
]

# Queries for Google CSE (save quota for highest-value searches)
GOOGLE_CSE_AUTHOR_QUERIES = [
    'author "official site" email contact',
    'novelist personal website email',
    'writer contact "get in touch" bio',
]

# Meta-content blacklist to avoid blog posts/guides
BLACKLIST_TERMS = [
    "blogpost", "how-to", "guide", "article", "listing", "directory", 
    "review", "roundup", "tips", "tricks", "rontar.com", "langfaq.com",
    "englishsumup.com", "grammarsir.com", "englishoverview.com"
]

def search_duckduckgo(query: str, max_results: int = 10) -> list[dict]:
    """
    Scrapes DuckDuckGo HTML search results.
    No API key required. Completely free forever.
    Returns list of {title, url, snippet} dicts.
    """
    headers = {
        "User-Agent": ua.random,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://duckduckgo.com/",
        "DNT": "1"
    }
    params = {
        "q": query,
        "kl": "us-en",    # region
        "kp": "-1",       # safe search off
        "k1": "-1",       # ads off
    }

    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params=params,
            headers=headers,
            timeout=15,
            follow_redirects=True
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for result in soup.select(".result__body")[:max_results]:
            title_el   = result.select_one(".result__title")
            url_el     = result.select_one(".result__url")
            snippet_el = result.select_one(".result__snippet")

            title   = title_el.get_text(strip=True)   if title_el   else ""
            url     = url_el.get_text(strip=True)     if url_el     else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            if title and url:
                results.append({
                    "title":   title,
                    "url":     f"https://{url}" if not url.startswith("http") else url,
                    "snippet": snippet
                })

        # Polite delay — avoid getting soft-blocked
        time.sleep(uniform(2.0, 4.0))
        return results

    except httpx.HTTPStatusError as e:
        logger.warning(f"DuckDuckGo returned {e.response.status_code} for query: {query}")
        return []
    except Exception as e:
        logger.warning(f"DuckDuckGo scrape failed: {e}")
        return []

def search_google_custom(query: str, max_results: int = 10) -> list[dict]:
    """
    Uses Google Custom Search JSON API.
    Free tier: 100 queries/day, no credit card needed.
    Falls back silently if quota exceeded.
    """
    if not settings.GOOGLE_CSE_API_KEY or not settings.GOOGLE_CSE_ID:
        logger.debug("Google CSE not configured — skipping")
        return []

    try:
        response = httpx.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": settings.GOOGLE_CSE_API_KEY,
                "cx":  settings.GOOGLE_CSE_ID,
                "q":   query,
                "num": min(max_results, 10)  # API max is 10 per call
            },
            timeout=10
        )

        # Quota exceeded — degrade gracefully, don't crash
        if response.status_code == 429:
            logger.warning("Google CSE daily quota exceeded (100/day). Falling back to DuckDuckGo for remaining searches.")
            return search_duckduckgo(query, max_results)

        response.raise_for_status()
        items = response.json().get("items", [])

        return [
            {
                "title":   item.get("title", ""),
                "url":     item.get("link", ""),
                "snippet": item.get("snippet", "")
            }
            for item in items
        ]

    except Exception as e:
        logger.warning(f"Google CSE failed: {e} — falling back to DuckDuckGo")
        return search_duckduckgo(query, max_results)

def search_authors_via_web(query: str) -> list[dict]:
    """
    Tries Google CSE first (better results, limited quota),
    falls back to DuckDuckGo automatically (unlimited, free).
    """
    results = search_google_custom(query)
    if not results:
        results = search_duckduckgo(query)
    return results

class Discoverer:
    def __init__(self):
        self.ua = ua
        self.sources = [
            self._discover_google_books,
            self._discover_goodreads,
            self._discover_web_search
        ]

    def find_authors(self, target: int = 50) -> list[dict]:
        discovered = []
        random.shuffle(self.sources)
        
        for source_fn in self.sources:
            if len(discovered) >= target:
                break
            try:
                results = source_fn(target - len(discovered))
                discovered.extend(results)
                logger.info(f"Discovered {len(results)} authors from {source_fn.__name__}")
            except Exception as e:
                logger.error(f"Source {source_fn.__name__} failed: {e}")
        
        return discovered[:target]

    def _discover_google_books(self, limit: int) -> list[dict]:
        queries = [
            "African fiction author 2023", "debut novelist 2024",
            "romance author Nigeria", "thriller author Kenya",
            "historical fiction author 2024", "biography author"
        ]
        query = random.choice(queries)
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults={min(limit, 40)}"
        
        authors = []
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(url)
                data = resp.json()
                for item in data.get("items", []):
                    info = item.get("volumeInfo", {})
                    if info.get("authors"):
                        authors.append({
                            "name": info["authors"][0],
                            "book_title": info.get("title"),
                            "description": info.get("description", ""),
                            "source_platform": "Google Books"
                        })
        except Exception as e:
            logger.error(f"Google Books API discovery failed: {e}")
        return authors

    def _discover_goodreads(self, limit: int) -> list[dict]:
        # Scrape Goodreads with Playwright
        authors = []
        if limit <= 0: return authors
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=self.ua.random)
                page.goto("https://www.goodreads.com/book/new_releases")
                # Simple extraction logic (mocking actual CSS selection for brevity)
                browser.close()
        except Exception as e:
            logger.error(f"Goodreads discovery failed: {e}")
        return authors

    def _discover_web_search(self, limit: int) -> list[dict]:
        # Combine Google CSE queries and DuckDuckGo queries for discovery
        all_queries = GOOGLE_CSE_AUTHOR_QUERIES + DUCKDUCKGO_AUTHOR_QUERIES
        query = random.choice(all_queries)
        
        web_results = search_authors_via_web(query)
        authors = []
        
        for result in web_results:
            if len(authors) >= limit: break
            
            url = result.get("url", "").lower()
            snippet = result.get("snippet", "").lower()
            title = result.get("title", "").lower()

            # Apply blacklist filter
            if any(term in url or term in snippet or term in title for term in BLACKLIST_TERMS):
                logger.info(f"Skipping blacklisted or low-signal result: {url}")
                continue
            
            # Use simple heuristic to extract author name from title
            raw_title = result.get("title", "")
            name = raw_title.split("by")[-1].strip() if "by" in raw_title else raw_title
            name = name.split("|")[0].strip() # Clean titles like "Author Name | Website"
            
            authors.append({
                "name": name,
                "book_title": None, # Could extract from snippet if needed
                "description": result.get("snippet", ""),
                "url": result.get("url"),
                "source_platform": "Web Search"
            })
            
        return authors

discoverer = Discoverer()

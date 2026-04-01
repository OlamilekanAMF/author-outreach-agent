import httpx
import random
import time
from random import uniform
from config.settings import settings
from gmail_channel.gmail_dedup import gmail_dedup
from fake_useragent import UserAgent
import logging

logger = logging.getLogger(__name__)

class GmailDiscoverer:
    def __init__(self):
        self.ua = UserAgent()
        self.sources = [
            self._discover_goodreads_listopia,
            self._discover_open_library,
            self._discover_loc,
            self._discover_gutendex
        ]

    def find_gmail_authors(self, target: int = 20) -> list[dict]:
        discovered = []
        random.shuffle(self.sources)
        
        for source_fn in self.sources:
            if len(discovered) >= target:
                break
            try:
                needed = target - len(discovered)
                results = source_fn(needed)
                
                for stub in results:
                    name = stub.get("name")
                    # Deduplication check
                    if gmail_dedup.is_name_contacted_anywhere(name):
                        continue
                    
                    discovered.append(stub)
                    if len(discovered) >= target:
                        break
                
                logger.info(f"[Gmail] Discovered {len(results)} candidates from {source_fn.__name__}")
                time.sleep(uniform(1.5, 4.0))
            except Exception as e:
                logger.error(f"[Gmail] Source {source_fn.__name__} failed: {e}")
        
        if len(discovered) < target:
            logger.warning(f"[Gmail] Only found {len(discovered)} unique authors out of {target} requested.")
            
        return discovered[:target]

    def _discover_goodreads_listopia(self, limit: int) -> list[dict]:
        lists = [
            "https://www.goodreads.com/list/show/1.Best_Books_Ever",
            "https://www.goodreads.com/list/show/6472.African_Literature",
            "https://www.goodreads.com/list/show/2681.Best_Self_Help_Books"
        ]
        # Mocking for now, in reality would use BeautifulSoup/Playwright
        return []

    def _discover_open_library(self, limit: int) -> list[dict]:
        subjects = ["poetry", "short_stories", "young_adult", "christian_fiction", "african_history", "memoir"]
        subject = random.choice(subjects)
        url = f"https://openlibrary.org/subjects/{subject}.json?limit={limit + 10}"
        
        authors = []
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
                for work in data.get("works", []):
                    if work.get("authors"):
                        authors.append({
                            "name": work["authors"][0]["name"],
                            "book_title": work.get("title"),
                            "description": "", # Open Library subjects don't give full bios usually
                            "source_platform": "Open Library"
                        })
        except Exception as e:
            logger.error(f"Open Library discovery failed: {e}")
        return authors

    def _discover_loc(self, limit: int) -> list[dict]:
        genres = ["fiction", "biography", "history", "poetry"]
        genre = random.choice(genres)
        url = f"https://www.loc.gov/books/?fo=json&q={genre}+author&c={limit}"
        
        authors = []
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("results", []):
                    if item.get("contributor"):
                        authors.append({
                            "name": item["contributor"][0],
                            "book_title": item.get("title"),
                            "description": "; ".join(item.get("subject", [])),
                            "source_platform": "Library of Congress"
                        })
        except Exception as e:
            logger.error(f"LOC discovery failed: {e}")
        return authors

    def _discover_gutendex(self, limit: int) -> list[dict]:
        genres = ["fiction", "history", "biography"]
        genre = random.choice(genres)
        url = f"https://gutendex.com/books/?search={genre}"
        
        authors = []
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
                for book in data.get("results", []):
                    if book.get("authors"):
                        authors.append({
                            "name": book["authors"][0]["name"],
                            "book_title": book.get("title"),
                            "description": "Classic/Public Domain seed",
                            "source_platform": "Project Gutenberg"
                        })
        except Exception as e:
            logger.error(f"Gutendex discovery failed: {e}")
        return authors

gmail_discoverer = GmailDiscoverer()

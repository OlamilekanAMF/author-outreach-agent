"""
sheets_reader.py — Reads dashboard data directly from Google Sheets.
Drop this in your project root alongside app.py.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

logger = logging.getLogger(__name__)

# Column indices for Authors sheet (0-based)
AUTHORS_COLS = {
    "id": 0, "full_name": 1, "email": 2, "email_source": 3,
    "email_verified": 4, "verification_result": 5, "book_titles": 6,
    "book_description": 7, "genres": 8, "website_url": 9, "social_url": 10,
    "source_platform": 11, "contacted_at": 12, "email_status": 13,
    "email_sent_at": 14, "subject": 15, "run_date": 16,
    "open_detected": 17, "open_detected_at": 18, "replied": 19,
    "followup_sent": 20, "followup_sent_at": 21, "followup_status": 22
}

# Column indices for Gmail Channel sheet (0-based)
GMAIL_COLS = {
    "id": 0, "full_name": 1, "email": 2, "email_source": 3,
    "email_verified": 4, "verification_result": 5, "book_titles": 6,
    "book_description": 7, "book_title2": 8, "genres": 9,
    "website_url": 10, "social_url": 11, "source_platform": 12,
    "contacted_at": 13, "email_status": 14, "email_sent_at": 15,
    "subject": 16, "run_date": 17, "open_detected": 18,
    "open_detected_at": 19, "replied": 20, "followup_sent": 21,
    "followup_sent_at": 22, "followup_status": 23, "channel": 24
}

# Daily Summary columns (0-based)
SUMMARY_COLS = {
    "date": 0, "discovered": 1, "valid_emails": 2, "sent": 3,
    "failed": 4, "skipped": 5, "followups_sent": 6, "opens": 7,
    "replies": 8, "sources": 9, "cost": 10, "errors": 11
}


class SheetsReader:
    def __init__(self):
        self._client = None
        self._sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")

    def _get_client(self):
        if self._client:
            return self._client
        json_content = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not json_content:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set")
        info = json.loads(json_content)
        creds = Credentials.from_service_account_info(info, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])
        self._client = gspread.authorize(creds)
        return self._client

    def _get_sheet(self):
        return self._get_client().open_by_key(self._sheet_id)

    def _get_rows(self, worksheet_name):
        """Get all rows from a worksheet, skipping the header."""
        try:
            ws = self._get_sheet().worksheet(worksheet_name)
            return ws.get_all_values()[1:]  # skip header row
        except Exception as e:
            logger.error(f"Failed to read {worksheet_name}: {e}")
            return []

    def _row_to_author(self, row, cols, channel):
        """Convert a sheet row to an author dict."""
        def get(key):
            idx = cols.get(key, -1)
            if idx < 0 or idx >= len(row):
                return ""
            return row[idx]

        return {
            "id": get("id"),
            "full_name": get("full_name"),
            "email": get("email"),
            "email_status": get("email_status") or "unknown",
            "contacted_at": get("contacted_at"),
            "open_detected": get("open_detected").lower() == "true",
            "open_detected_at": get("open_detected_at"),
            "replied": get("replied").lower() == "true",
            "followup_sent": get("followup_sent").lower() == "true",
            "followup_sent_at": get("followup_sent_at"),
            "followup_status": get("followup_status"),
            "genres": get("genres"),
            "source_platform": get("source_platform"),
            "channel": channel
        }

    def get_all_authors(self):
        main_rows  = self._get_rows("Authors")
        gmail_rows = self._get_rows("Gmail Channel")

        main  = [self._row_to_author(r, AUTHORS_COLS, "main")  for r in main_rows  if r and r[0]]
        gmail = [self._row_to_author(r, GMAIL_COLS,   "gmail") for r in gmail_rows if r and r[0]]
        return main + gmail

    def get_overview_stats(self):
        try:
            authors = self.get_all_authors()
            main   = [a for a in authors if a["channel"] == "main"]
            gmail  = [a for a in authors if a["channel"] == "gmail"]

            def stats(lst):
                return {
                    "total":     len(lst),
                    "sent":      sum(1 for a in lst if a["email_status"] == "sent"),
                    "opens":     sum(1 for a in lst if a["open_detected"]),
                    "replies":   sum(1 for a in lst if a["replied"]),
                    "followups": sum(1 for a in lst if a["followup_sent"]),
                }

            ms = stats(main)
            gs = stats(gmail)
            return {
                "main_total":    ms["total"],   "main_sent":      ms["sent"],
                "main_opens":    ms["opens"],   "main_replies":   ms["replies"],
                "main_followups": ms["followups"],
                "gmail_total":   gs["total"],   "gmail_sent":     gs["sent"],
                "gmail_opens":   gs["opens"],   "gmail_replies":  gs["replies"],
                "gmail_followups": gs["followups"],
                "total_sent":    ms["sent"]  + gs["sent"],
                "total_opens":   ms["opens"] + gs["opens"],
                "total_replies": ms["replies"] + gs["replies"],
            }
        except Exception as e:
            logger.error(f"get_overview_stats error: {e}")
            return {k: 0 for k in [
                "main_total","main_sent","main_opens","main_replies","main_followups",
                "gmail_total","gmail_sent","gmail_opens","gmail_replies","gmail_followups",
                "total_sent","total_opens","total_replies"
            ]}

    def get_daily_send_counts(self, days=30):
        try:
            authors   = self.get_all_authors()
            cutoff    = datetime.utcnow() - timedelta(days=days)
            result    = {}

            for a in authors:
                raw = a.get("contacted_at", "")
                if not raw:
                    continue
                try:
                    dt = datetime.fromisoformat(raw[:10])
                except Exception:
                    continue
                if dt < cutoff:
                    continue
                day = raw[:10]
                if day not in result:
                    result[day] = {"main": 0, "gmail": 0}
                result[day][a["channel"]] += 1

            return [{"day": k, "main": v["main"], "gmail": v["gmail"]}
                    for k, v in sorted(result.items())]
        except Exception as e:
            logger.error(f"get_daily_send_counts error: {e}")
            return []

    def get_genre_performance(self):
        try:
            authors = self.get_all_authors()
            stats   = {}
            for a in authors:
                raw_genres = a.get("genres", "") or "Unknown"
                for g in [x.strip() for x in raw_genres.split(",") if x.strip()]:
                    if g not in stats:
                        stats[g] = {"total": 0, "opens": 0, "replies": 0}
                    stats[g]["total"] += 1
                    if a["open_detected"]:
                        stats[g]["opens"] += 1
                    if a["replied"]:
                        stats[g]["replies"] += 1

            top = sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True)[:10]
            return [{"genre": k, **v} for k, v in top]
        except Exception as e:
            logger.error(f"get_genre_performance error: {e}")
            return []

    def get_weekly_growth(self):
        try:
            authors = self.get_all_authors()
            now     = datetime.utcnow()
            week_start      = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0)
            last_week_start = week_start - timedelta(days=7)

            this_week = last_week = 0
            for a in authors:
                raw = a.get("contacted_at", "")
                if not raw:
                    continue
                try:
                    dt = datetime.fromisoformat(raw[:19])
                except Exception:
                    continue
                if dt >= week_start:
                    this_week += 1
                elif dt >= last_week_start:
                    last_week += 1

            growth = ((this_week - last_week) / last_week * 100) if last_week > 0 else 100
            return {"this_week": this_week, "last_week": last_week, "growth": round(growth, 1)}
        except Exception as e:
            logger.error(f"get_weekly_growth error: {e}")
            return {"this_week": 0, "last_week": 0, "growth": 0}

    def get_status_breakdown(self):
        try:
            authors   = self.get_all_authors()
            breakdown = {}
            for a in authors:
                s = a.get("email_status") or "unknown"
                breakdown[s] = breakdown.get(s, 0) + 1
            return breakdown
        except Exception as e:
            logger.error(f"get_status_breakdown error: {e}")
            return {}

    def get_authors_paginated(self, page=1, per_page=20,
                               status_filter=None, search_query=None, channel="all"):
        try:
            authors = self.get_all_authors()

            if channel != "all":
                authors = [a for a in authors if a["channel"] == channel]
            if status_filter:
                authors = [a for a in authors if a["email_status"] == status_filter]
            if search_query:
                q = search_query.lower()
                authors = [a for a in authors
                           if q in a["full_name"].lower() or q in a["email"].lower()]

            # Sort newest first
            authors.sort(key=lambda a: a.get("contacted_at") or "", reverse=True)

            total  = len(authors)
            start  = (page - 1) * per_page
            end    = start + per_page
            pages  = max(1, (total + per_page - 1) // per_page)

            return {
                "authors": authors[start:end],
                "total": total,
                "pages": pages,
                "current_page": page
            }
        except Exception as e:
            logger.error(f"get_authors_paginated error: {e}")
            return {"authors": [], "total": 0, "pages": 0, "current_page": page}

    def get_activity_log(self, limit=50):
        try:
            authors = self.get_all_authors()
            events  = []

            for a in authors:
                if a.get("email_status") == "sent" and a.get("contacted_at"):
                    events.append({
                        "type": "email_sent",
                        "full_name": a["full_name"],
                        "timestamp": a["contacted_at"],
                        "channel": a["channel"]
                    })
                if a.get("open_detected") and a.get("open_detected_at"):
                    events.append({
                        "type": "open",
                        "full_name": a["full_name"],
                        "timestamp": a["open_detected_at"],
                        "channel": a["channel"]
                    })

            events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
            return events[:limit]
        except Exception as e:
            logger.error(f"get_activity_log error: {e}")
            return []

    def get_daily_summaries(self, limit=30):
        try:
            rows = self._get_rows("Daily Summary")
            result = []
            for row in rows[-limit:]:
                if not row or not row[0]:
                    continue
                def g(i): return row[i] if i < len(row) else ""
                result.append({
                    "date": g(0), "discovered": g(1), "valid_emails": g(2),
                    "sent": g(3), "failed": g(4), "skipped": g(5),
                    "followups_sent": g(6), "opens": g(7), "replies": g(8),
                    "sources": g(9), "cost": g(10), "errors": g(11)
                })
            return list(reversed(result))
        except Exception as e:
            logger.error(f"get_daily_summaries error: {e}")
            return []

    def get_author_detail(self, author_id):
        try:
            for channel, ws_name, cols in [
                ("main", "Authors", AUTHORS_COLS),
                ("gmail", "Gmail Channel", GMAIL_COLS)
            ]:
                rows = self._get_rows(ws_name)
                for row in rows:
                    if row and row[0] == author_id:
                        return self._row_to_author(row, cols, channel)
            return None
        except Exception as e:
            logger.error(f"get_author_detail error: {e}")
            return None

    def get_system_logs(self, limit=100):
        # System logs live in SQLite only; return empty for now
        return []

    def get_top_leads(self, limit=10):
        try:
            authors = self.get_all_authors()
            leads   = [a for a in authors if a["replied"] or a["open_detected"]]
            # Score: reply=10pts, open=1pt
            def score(a):
                return (10 if a["replied"] else 0) + (1 if a["open_detected"] else 0)
            leads.sort(key=score, reverse=True)
            return leads[:limit]
        except Exception as e:
            logger.error(f"get_top_leads error: {e}")
            return []

    def get_pending_approvals(self):
        # Approval workflow uses SQLite; return empty
        return []

    def get_ab_test_stats(self):
        # A/B variant data not in sheets; return empty
        return []


sheets_reader = SheetsReader()

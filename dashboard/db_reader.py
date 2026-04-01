import sqlite3
import os
import json
from datetime import datetime, timedelta
from config.settings import settings

DB_PATH = settings.DB_PATH

class DBReader:
    def __init__(self):
        self.db_path = DB_PATH

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn

    def get_overview_stats(self):
        conn = self._get_connection()
        stats = {}
        
        # Combine counts from both tables
        for table in ['contacted_authors', 'gmail_contacted_authors']:
            try:
                row = conn.execute(f"""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN email_status = 'sent' THEN 1 ELSE 0 END) as sent,
                        SUM(CASE WHEN open_detected = 1 THEN 1 ELSE 0 END) as opens,
                        SUM(CASE WHEN replied = 1 THEN 1 ELSE 0 END) as replies,
                        SUM(CASE WHEN followup_sent = 1 THEN 1 ELSE 0 END) as followups
                    FROM {table}
                """).fetchone()
                
                prefix = 'main_' if table == 'contacted_authors' else 'gmail_'
                stats[prefix + 'total'] = row['total'] or 0
                stats[prefix + 'sent'] = row['sent'] or 0
                stats[prefix + 'opens'] = row['opens'] or 0
                stats[prefix + 'replies'] = row['replies'] or 0
                stats[prefix + 'followups'] = row['followups'] or 0
            except:
                prefix = 'main_' if table == 'contacted_authors' else 'gmail_'
                stats[prefix + 'total'] = 0
                stats[prefix + 'sent'] = 0
                stats[prefix + 'opens'] = 0
                stats[prefix + 'replies'] = 0
                stats[prefix + 'followups'] = 0

        stats['total_sent'] = stats['main_sent'] + stats['gmail_sent']
        stats['total_opens'] = stats['main_opens'] + stats['gmail_opens']
        stats['total_replies'] = stats['main_replies'] + stats['gmail_replies']
        
        conn.close()
        return stats

    def get_daily_send_counts(self, days=30):
        conn = self._get_connection()
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query = """
            SELECT date(contacted_at) as day, COUNT(*) as count, 'main' as channel
            FROM contacted_authors
            WHERE contacted_at >= ?
            GROUP BY day
            UNION ALL
            SELECT date(contacted_at) as day, COUNT(*) as count, 'gmail' as channel
            FROM gmail_contacted_authors
            WHERE contacted_at >= ?
            GROUP BY day
            ORDER BY day ASC
        """
        
        rows = conn.execute(query, (start_date.isoformat(), start_date.isoformat())).fetchall()
        conn.close()
        
        result = {}
        for row in rows:
            day = row['day']
            if day not in result:
                result[day] = {'main': 0, 'gmail': 0}
            result[day][row['channel']] = row['count']
            
        return [{"day": k, "main": v['main'], "gmail": v['gmail']} for k, v in sorted(result.items())]

    def get_genre_performance(self):
        conn = self._get_connection()
        query = """
            SELECT genres, COUNT(*) as total, 
                   SUM(CASE WHEN open_detected = 1 THEN 1 ELSE 0 END) as opens,
                   SUM(CASE WHEN replied = 1 THEN 1 ELSE 0 END) as replies
            FROM contacted_authors GROUP BY genres
            UNION ALL
            SELECT genres, COUNT(*) as total,
                   SUM(CASE WHEN open_detected = 1 THEN 1 ELSE 0 END) as opens,
                   SUM(CASE WHEN replied = 1 THEN 1 ELSE 0 END) as replies
            FROM gmail_contacted_authors GROUP BY genres
        """
        rows = conn.execute(query).fetchall()
        conn.close()
        
        genres_stats = {}
        for row in rows:
            raw_genres = row['genres'] or 'Unknown'
            # Split and normalize
            genre_list = [g.strip() for g in raw_genres.split(',') if g.strip()]
            for g in genre_list:
                if g not in genres_stats:
                    genres_stats[g] = {'total': 0, 'opens': 0, 'replies': 0}
                genres_stats[g]['total'] += row['total']
                genres_stats[g]['opens'] += row['opens']
                genres_stats[g]['replies'] += row['replies']
        
        # Sort by total and take top 10
        sorted_genres = sorted(genres_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:10]
        return [{"genre": k, **v} for k, v in sorted_genres]

    def get_weekly_growth(self):
        conn = self._get_connection()
        now = datetime.utcnow()
        this_week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        last_week_start = this_week_start - timedelta(days=7)
        
        def get_count_for_range(start, end):
            q = """
                SELECT COUNT(*) FROM (
                    SELECT id FROM contacted_authors WHERE contacted_at >= ? AND contacted_at < ?
                    UNION ALL
                    SELECT id FROM gmail_contacted_authors WHERE contacted_at >= ? AND contacted_at < ?
                )
            """
            return conn.execute(q, (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat())).fetchone()[0]

        this_week = get_count_for_range(this_week_start, now)
        last_week = get_count_for_range(last_week_start, this_week_start)
        conn.close()
        
        growth = ((this_week - last_week) / last_week * 100) if last_week > 0 else 100
        return {"this_week": this_week, "last_week": last_week, "growth": round(growth, 1)}

    def get_ab_test_stats(self):
        conn = self._get_connection()
        query = """
            SELECT 
                ab_variant as variant,
                COUNT(*) as total_sent,
                SUM(CASE WHEN open_detected = 1 THEN 1 ELSE 0 END) as total_opens,
                SUM(CASE WHEN replied = 1 THEN 1 ELSE 0 END) as total_replies
            FROM (
                SELECT id, email_status, open_detected, replied, ab_variant FROM contacted_authors
                UNION ALL
                SELECT id, email_status, open_detected, replied, ab_variant FROM gmail_contacted_authors
            )
            WHERE email_status = 'sent' AND ab_variant IS NOT NULL
            GROUP BY ab_variant
        """
        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_pending_approvals(self):
        conn = self._get_connection()
        query = """
            SELECT id, full_name, email, source_platform, contacted_at as found_at, 'main' as channel
            FROM contacted_authors WHERE approval_status = 'pending'
            UNION ALL
            SELECT id, full_name, email, source_platform, contacted_at as found_at, 'gmail' as channel
            FROM gmail_contacted_authors WHERE approval_status = 'pending'
            ORDER BY found_at DESC
        """
        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_approval_status(self, author_id, status):
        conn = self._get_connection()
        conn.execute("PRAGMA query_only = OFF") # Ensure we can write
        
        # Try both tables
        updated = conn.execute("UPDATE contacted_authors SET approval_status = ? WHERE id = ?", (status, author_id)).rowcount
        if not updated:
            updated = conn.execute("UPDATE gmail_contacted_authors SET approval_status = ? WHERE id = ?", (status, author_id)).rowcount
        
        conn.commit()
        conn.close()
        return bool(updated)

    def get_status_breakdown(self):
        conn = self._get_connection()
        query = """
            SELECT email_status, COUNT(*) as count FROM contacted_authors GROUP BY email_status
            UNION ALL
            SELECT email_status, COUNT(*) as count FROM gmail_contacted_authors GROUP BY email_status
        """
        rows = conn.execute(query).fetchall()
        conn.close()
        
        breakdown = {}
        for row in rows:
            status = row['email_status'] or 'unknown'
            breakdown[status] = breakdown.get(status, 0) + row['count']
            
        return breakdown

    def get_authors_paginated(self, page=1, per_page=20, status_filter=None, search_query=None, channel='all'):
        conn = self._get_connection()
        offset = (page - 1) * per_page
        
        # Build dynamic query
        tables = []
        if channel in ['all', 'main']: tables.append(('contacted_authors', 'main'))
        if channel in ['all', 'gmail']: tables.append(('gmail_contacted_authors', 'gmail'))
        
        base_queries = []
        params = []
        
        for table, ch_name in tables:
            q = f"SELECT id, full_name, email, email_status, contacted_at, open_detected, replied, '{ch_name}' as channel FROM {table}"
            where_clauses = []
            if status_filter:
                where_clauses.append("email_status = ?")
                params.append(status_filter)
            if search_query:
                where_clauses.append("(full_name LIKE ? OR email LIKE ?)")
                params.append(f"%{search_query}%")
                params.append(f"%{search_query}%")
            
            if where_clauses:
                q += " WHERE " + " AND ".join(where_clauses)
            base_queries.append(q)
            
        final_query = " UNION ALL ".join(base_queries) + " ORDER BY contacted_at DESC LIMIT ? OFFSET ?"
        count_query = "SELECT COUNT(*) as total FROM (" + " UNION ALL ".join(base_queries) + ")"
        
        # Count params are the same as data params minus limit/offset
        total = conn.execute(count_query, params).fetchone()['total']
        
        data_params = params + [per_page, offset]
        rows = conn.execute(final_query, data_params).fetchall()
        
        conn.close()
        return {
            "authors": [dict(row) for row in rows],
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "current_page": page
        }

    def get_author_detail(self, author_id):
        conn = self._get_connection()
        # Search in both tables
        author = conn.execute("SELECT *, 'main' as channel FROM contacted_authors WHERE id = ?", (author_id,)).fetchone()
        if not author:
            author = conn.execute("SELECT *, 'gmail' as channel FROM gmail_contacted_authors WHERE id = ?", (author_id,)).fetchone()
        
        conn.close()
        return dict(author) if author else None

    def get_activity_log(self, limit=50):
        # Recent sends and opens
        conn = self._get_connection()
        query = """
            SELECT 'email_sent' as type, full_name, contacted_at as timestamp, 'main' as channel 
            FROM contacted_authors WHERE email_status = 'sent'
            UNION ALL
            SELECT 'email_sent' as type, full_name, contacted_at as timestamp, 'gmail' as channel 
            FROM gmail_contacted_authors WHERE email_status = 'sent'
            UNION ALL
            SELECT 'open' as type, full_name, open_detected_at as timestamp, 'main' as channel 
            FROM contacted_authors WHERE open_detected = 1
            UNION ALL
            SELECT 'open' as type, full_name, open_detected_at as timestamp, 'gmail' as channel 
            FROM gmail_contacted_authors WHERE open_detected = 1
            ORDER BY timestamp DESC LIMIT ?
        """
        rows = conn.execute(query, (limit,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_email_draft(self, author_id):
        conn = self._get_connection()
        draft = conn.execute("SELECT * FROM email_drafts WHERE author_id = ?", (author_id,)).fetchone()
        if not draft:
            draft = conn.execute("SELECT * FROM gmail_email_drafts WHERE author_id = ?", (author_id,)).fetchone()
        conn.close()
        return dict(draft) if draft else None

    def get_system_logs(self, limit=100):
        conn = self._get_connection()
        rows = conn.execute("SELECT * FROM system_logs ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_top_leads(self, limit=10):
        conn = self._get_connection()
        query = """
            SELECT id, full_name, email, lead_score, reply_sentiment, 'main' as channel
            FROM contacted_authors WHERE lead_score > 0 OR reply_sentiment = 'interested'
            UNION ALL
            SELECT id, full_name, email, lead_score, reply_sentiment, 'gmail' as channel
            FROM gmail_contacted_authors WHERE lead_score > 0 OR reply_sentiment = 'interested'
            ORDER BY (CASE WHEN reply_sentiment = 'interested' THEN 1000 ELSE lead_score END) DESC
            LIMIT ?
        """
        rows = conn.execute(query, (limit,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

db_reader = DBReader()

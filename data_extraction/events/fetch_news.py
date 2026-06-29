#!/usr/bin/env python3
"""fetch_news.py — Market news headlines from RSS feeds (ET, Pulse, Moneycontrol).
Forward-accumulating: feeds carry the latest ~50 items, so run periodically to
build history. Dedup by link. Feeds NLP/sentiment downstream.

Run:  py -3.14 events/fetch_news.py
"""
import sqlite3, time
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

import requests

DB_PATH = Path(r"D:\marketDB\db\market.db")
FEEDS = {
    "ET-markets":  "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "ET-stocks":   "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "Pulse":       "https://pulse.zerodha.com/feed.php",
    "MC-markets":  "https://www.moneycontrol.com/rss/marketreports.xml",
    "MC-business": "https://www.moneycontrol.com/rss/business.xml",
}


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS news_headlines (
        link TEXT PRIMARY KEY, title TEXT, published TEXT, source TEXT, fetched_at TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_pub ON news_headlines(published)")
    conn.commit()


def parse_pubdate(s):
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return s.strip()[:25]


def main():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    ensure(conn)
    now = datetime.now().isoformat()
    tot = 0

    for src, url in FEEDS.items():
        try:
            xml = s.get(url, timeout=20).content
            root = ET.fromstring(xml)
            rows = []
            for item in root.iter("item"):
                def g(tag):
                    e = item.find(tag)
                    return e.text.strip() if (e is not None and e.text) else None
                link, title = g("link"), g("title")
                if not link or not title:
                    continue
                rows.append((link, title, parse_pubdate(g("pubDate")), src, now))
            if rows:
                conn.executemany(
                    "INSERT OR REPLACE INTO news_headlines (link,title,published,source,fetched_at) "
                    "VALUES (?,?,?,?,?)", rows)
                conn.commit()
                tot += len(rows)
            print(f"  {src}: {len(rows)} items", flush=True)
        except Exception as e:
            print(f"  {src}: ERR {str(e)[:60]}", flush=True)
        time.sleep(0.5)

    n = conn.execute("SELECT COUNT(*) FROM news_headlines").fetchone()[0]
    conn.close()
    print(f"DONE: news_headlines +{tot} this run, {n:,} total", flush=True)


if __name__ == "__main__":
    main()

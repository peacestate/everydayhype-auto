"""Step 1 — pull FRESH trending AI/tech candidates (no API key).
Dedicated AI-news RSS feeds + recent (not evergreen) Hacker News. Recency-filtered so stale items drop."""
import json, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "Mozilla/5.0 (compatible; everydayhypehq-bot/1.0)"}
MAX_AGE_DAYS = 4

# Satire / parody / humor sources — NEVER post these as real news (HN surfaces them often).
SATIRE_DOMAINS = (
    "aiclambake.com", "theonion.com", "babylonbee.com", "clickhole.com",
    "reductress.com", "thehardtimes.net", "thedailymash.co.uk", "newsthump.com",
    "thebeaverton.com", "waterfordwhispersnews.com", "private-eye.co.uk",
    "hard-drive.net", "thingstheonionjustdid.com", "betootaadvocate.com",
)
# Title cues that scream satire even off-domain.
SATIRE_TITLE_CUES = ("satire", "parody", "the onion", "babylon bee")

def _is_satire(url, title):
    u = (url or "").lower(); t = (title or "").lower()
    return any(d in u for d in SATIRE_DOMAINS) or any(c in t for c in SATIRE_TITLE_CUES)

def _get(url, parse="json"):
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "replace")
    return json.loads(data) if parse == "json" else data

def _fresh(pubdate_str):
    if not pubdate_str: return True            # keep if unknown
    try:
        dt = parsedate_to_datetime(pubdate_str)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) <= timedelta(days=MAX_AGE_DAYS)
    except Exception:
        return True

def from_hn(limit=20):
    """RECENT AI stories (search_by_date), not evergreen front-page."""
    cutoff = int(time.time()) - MAX_AGE_DAYS * 86400
    out = []
    for q in ("AI", "OpenAI", "Anthropic", "LLM OR GPT OR Gemini OR model"):
        try:
            d = _get("https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(
                {"query": q, "tags": "story", "numericFilters": f"points>40,created_at_i>{cutoff}"}))
            for h in d.get("hits", []):
                if h.get("title"):
                    out.append({"title": h["title"], "url": h.get("url") or
                                f'https://news.ycombinator.com/item?id={h.get("objectID")}',
                                "score": h.get("points", 0), "src": "hackernews"})
        except Exception as e:
            print("HN error", e)
    return out[:limit]

# dedicated AI-news feeds (curated > generic). googlenews uses a tight recent AI query.
RSS_FEEDS = {
    "the-decoder":   ("https://the-decoder.com/feed/", 72),
    "techcrunch-ai": ("https://techcrunch.com/category/artificial-intelligence/feed/", 70),
    "verge-ai":      ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", 70),
    "venturebeat-ai":("https://venturebeat.com/category/ai/feed/", 66),
    "mit-tr-ai":     ("https://www.technologyreview.com/topic/artificial-intelligence/feed/", 74),
    "ars-ai":        ("https://arstechnica.com/ai/feed/", 68),
    "wired-ai":      ("https://www.wired.com/feed/tag/ai/latest/rss", 66),
    "googlenews-ai": ("https://news.google.com/rss/search?q=(AI%20OR%20%22artificial%20intelligence%22)%20(launches%20OR%20unveils%20OR%20releases%20OR%20breakthrough%20OR%20raises%20OR%20announces)%20when:2d&hl=en-US&gl=US&ceid=US:en", 50),
}
def from_rss():
    out = []
    for src, (url, base) in RSS_FEEDS.items():
        try:
            root = ET.fromstring(_get(url, parse="xml"))
            for item in root.iter("item"):
                t = item.findtext("title"); link = item.findtext("link")
                if t and _fresh(item.findtext("pubDate")):
                    out.append({"title": t.strip(), "url": (link or "").strip(), "score": base, "src": src})
        except Exception as e:
            print("RSS error", src, e)
    return out

def fetch_candidates():
    cands = from_hn() + from_rss()
    seen, uniq, dropped = set(), [], 0
    for c in sorted(cands, key=lambda x: -x["score"]):
        if _is_satire(c["url"], c["title"]):
            dropped += 1; continue
        k = c["title"].lower()[:60]
        if k not in seen and c["url"]:
            seen.add(k); uniq.append(c)
    print(f"[s1] {len(uniq)} fresh unique candidates ({dropped} satire dropped)")
    return uniq[:45]

if __name__ == "__main__":
    for c in fetch_candidates()[:22]:
        print(f'{c["score"]:>5}  {c["src"]:<14} {c["title"][:78]}')

"""Step 1 — pull trending AI/tech candidates (no API key).
Hacker News (Algolia) gives engagement scores; RSS feeds give fresh coverage. Reddit best-effort."""
import json, urllib.request, urllib.parse, xml.etree.ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0 (compatible; everydayhypehq-bot/1.0)"}

def _get(url, parse="json"):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8", "replace")
    return json.loads(data) if parse == "json" else data

def from_hn(limit=25):
    out = []
    for tags, q in (("front_page", ""), ("story", "AI"), ("story", "OpenAI"), ("story", "Anthropic")):
        try:
            params = {"tags": tags}
            if q: params["query"] = q
            d = _get("https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(params))
            for h in d.get("hits", []):
                if h.get("title") and h.get("points", 0) >= 50:
                    out.append({"title": h["title"], "url": h.get("url") or
                                f'https://news.ycombinator.com/item?id={h.get("objectID")}',
                                "score": h.get("points", 0), "src": "hackernews"})
        except Exception as e:
            print("HN error", e)
    return out[:limit]

RSS_FEEDS = {
    "googlenews": "https://news.google.com/rss/search?q=artificial%20intelligence%20when:1d&hl=en-US&gl=US&ceid=US:en",
    "techcrunch": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "venturebeat": "https://venturebeat.com/category/ai/feed/",
    "arstechnica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
}
def from_rss(limit=30):
    out = []
    for src, url in RSS_FEEDS.items():
        try:
            xml = _get(url, parse="xml")
            root = ET.fromstring(xml)
            for item in root.iter("item"):
                t = item.findtext("title"); link = item.findtext("link")
                if t: out.append({"title": t.strip(), "url": (link or "").strip(),
                                  "score": 40, "src": src})   # baseline; brain ranks on merit
        except Exception as e:
            print("RSS error", src, e)
    return out[:limit]

def fetch_candidates():
    cands = from_hn() + from_rss()
    seen, uniq = set(), []
    for c in sorted(cands, key=lambda x: -x["score"]):
        k = c["title"].lower()[:60]
        if k not in seen:
            seen.add(k); uniq.append(c)
    print(f"[s1] {len(uniq)} unique candidates")
    return uniq[:40]

if __name__ == "__main__":
    for c in fetch_candidates()[:18]:
        print(f'{c["score"]:>5}  {c["src"]:<12} {c["title"][:80]}')

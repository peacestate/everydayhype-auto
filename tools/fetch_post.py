"""One-off: pull a specific Instagram post via the Graph API (read), download its image(s)/caption
so it can be reviewed. Finds posts whose caption contains KEYWORD (case-insensitive), paginating
back through your media. Writes images + caption + a metadata json to out/."""
import os, json, requests

G = "https://graph.facebook.com/v21.0"
TOKEN = os.environ["IG_ACCESS_TOKEN"]
UID = os.environ["IG_USER_ID"]
KW = os.environ.get("KEYWORD", "").lower().strip()
MAXPAGES = int(os.environ.get("MAXPAGES", "6"))   # ~6*50 = 300 most-recent posts

os.makedirs("out", exist_ok=True)

def get(url, **params):
    params["access_token"] = TOKEN
    return requests.get(url, params=params, timeout=60).json()

# paginate media
items, url, params = [], f"{G}/{UID}/media", {
    "fields": "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count", "limit": 50}
for _ in range(MAXPAGES):
    r = get(url, **params) if "access_token" not in params else requests.get(url, timeout=60).json()
    if "error" in r:
        print("API ERROR:", json.dumps(r["error"])); break
    items += r.get("data", [])
    nxt = r.get("paging", {}).get("next")
    if not nxt:
        break
    url, params = nxt, {}     # next url already carries token + cursor

print(f"fetched {len(items)} posts")
json.dump([{k: m.get(k) for k in ("id", "caption", "media_type", "permalink", "timestamp",
                                  "like_count", "comments_count")} for m in items],
          open("out/_all_media.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)

hits = [m for m in items if KW and KW in ((m.get("caption") or "") + " " + (m.get("timestamp") or "")).lower()]
print(f"matches for '{KW}': {len(hits)}")
for i, m in enumerate(hits[:3]):
    open(f"out/post{i}_caption.txt", "w", encoding="utf-8").write(
        f"{m.get('timestamp')}  likes={m.get('like_count')} comments={m.get('comments_count')}\n"
        f"{m.get('permalink')}\n\n{m.get('caption') or ''}")
    urls = []
    if m.get("media_type") == "CAROUSEL_ALBUM":
        ch = get(f"{G}/{m['id']}/children", fields="media_url,media_type")
        urls = [c["media_url"] for c in ch.get("data", []) if c.get("media_url")]
    elif m.get("media_url"):
        urls = [m["media_url"]]
    for j, u in enumerate(urls):
        ext = ".mp4" if ".mp4" in u.split("?")[0] else ".jpg"
        open(f"out/post{i}_slide{j}{ext}", "wb").write(requests.get(u, timeout=90).content)
    print(f"  post{i}: {m.get('timestamp')} — {len(urls)} media — {(m.get('caption') or '')[:60]}")

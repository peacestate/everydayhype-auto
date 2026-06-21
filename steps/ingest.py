"""Telegram example-ingest agent: you send screenshots of top-performing posts to the bot; this
reads each with a vision model, extracts the reusable WINNING PATTERN (topic/hook/headline/why),
and appends it to examples.md — so you 'train' the writer just by forwarding screenshots, no typing.
Runs on a cron in GitHub Actions (laptop off). Tracks a Telegram update offset so nothing is double-read."""
import json, base64, requests
from openai import OpenAI
import config as C

OFFSET_FILE = C.STATE / "tg_offset.txt"
EXAMPLES = C.ROOT / "examples.md"

def _api(method, **kw):
    return requests.post(f"https://api.telegram.org/bot{C.TG_TOKEN}/{method}", data=kw, timeout=60).json()

def _download(file_id):
    fp = _api("getFile", file_id=file_id)["result"]["file_path"]
    return requests.get(f"https://api.telegram.org/file/bot{C.TG_TOKEN}/{fp}", timeout=60).content

def _extract(img_bytes):
    client = OpenAI(api_key=C.OPENAI_API_KEY)
    b64 = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()
    sys = ("You analyze a screenshot of a high-performing social/news post and extract its REUSABLE "
           "pattern for a content library (capture the STYLE, never copy exact wording/facts). "
           "Return ONLY a markdown block exactly like:\n"
           "- TOPIC: <short>\n  HOOK: \"<grabby opener style>\"\n  HEADLINE STYLE: \"<bold CAPS shape>\"\n"
           "  WHY IT WORKS: <one line>")
    r = client.chat.completions.create(model="gpt-4o-mini", temperature=0.2, messages=[
        {"role": "system", "content": sys},
        {"role": "user", "content": [{"type": "text", "text": "Extract the winning pattern:"},
                                     {"type": "image_url", "image_url": {"url": b64, "detail": "low"}}]}])
    return r.choices[0].message.content.strip()

def run():
    if not C.TG_TOKEN:
        print("[ingest] no telegram token"); return
    offset = int(OFFSET_FILE.read_text().strip()) if OFFSET_FILE.exists() else 0
    upd = _api("getUpdates", offset=offset, allowed_updates=json.dumps(["message"]))
    updates = upd.get("result", [])
    added, last = 0, offset
    for u in updates:
        last = u["update_id"] + 1
        msg = u.get("message", {})
        photos = msg.get("photo")
        chat = (msg.get("chat") or {}).get("id")
        if not photos:
            continue
        try:
            block = _extract(_download(photos[-1]["file_id"]))   # largest size
            with open(EXAMPLES, "a", encoding="utf-8") as f:
                f.write("\n\n" + block + "\n")
            added += 1
            if chat:
                _api("sendMessage", chat_id=chat, text="✅ Learned from your example — added to the library.")
        except Exception as e:
            print("[ingest] one failed:", e)
    if last != offset:
        OFFSET_FILE.write_text(str(last))
    print(f"[ingest] {len(updates)} updates, {added} new examples added")

if __name__ == "__main__":
    run()

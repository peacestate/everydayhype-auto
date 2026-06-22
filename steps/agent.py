"""GitHub-side helper for the Telegram WEBHOOK architecture.

The Cloudflare Worker (worker/worker.js) is the instant Telegram brain — it owns all live Telegram
updates and handles taps/edits in ~1s. This module does the heavy / scheduled work GitHub is better
at, and NEVER calls getUpdates (the webhook owns that now):

  • publish_approved() — dispatched (publish.yml) the instant you tap ✅: posts the approved carousel
                         to Instagram, records the ledger, confirms back.
  • maintain()         — cron (every ~15 min): drains training messages the Worker stashed in
                         state/tg_queue.json into examples.md, and AUTO-POSTS a pending post once it
                         passes the deadline (the "almost 2 hours" safety net)."""
import json
import config as C
from steps import ingest, telegram as tg, pending, s6_publish, s2_brain

QUEUE_FILE = C.STATE / "tg_queue.json"

def _publish(p, reason):
    """Publish a pending/approved post to Instagram, record the ledger, report back."""
    pending.mark("posting")
    try:
        media_id = s6_publish.publish(p["image_urls"], p["caption"])
    except Exception as e:
        pending.mark("approved")  # leave it so a retry can pick it up
        tg.send_text(f"❌ Instagram post FAILED ({reason}): {e}", chat_id=p.get("chat_id"))
        print(f"[agent] publish failed: {e}"); return
    s2_brain.commit_ledger(p["plan"])
    pending.mark("posted")
    if p.get("control_msg_id"):
        tg.edit_text(p["control_msg_id"], f"✅ POSTED to Instagram (id {media_id}) — {reason}",
                     chat_id=p.get("chat_id"), reply_markup={"inline_keyboard": []})
    tg.send_text(f"✅ Posted carousel {media_id} — {reason}.", chat_id=p.get("chat_id"))
    print(f"[agent] PUBLISHED {media_id} ({reason})")

def publish_approved():
    """Run by publish.yml right after you tap ✅ (Worker set status='approved')."""
    p = pending.load()
    if not p or p.get("status") != "approved":
        print(f"[agent] nothing to publish (status={p and p.get('status')})"); return
    _publish(p, "you approved")

def _drain_queue():
    """Process training messages the Worker stashed (images/files/ideas) into examples.md."""
    if not QUEUE_FILE.exists():
        return 0
    try:
        msgs = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        msgs = []
    learned = 0
    for msg in msgs:
        try:
            block = ingest._handle(msg)
            if block:
                with open(ingest.EXAMPLES, "a", encoding="utf-8") as f:
                    f.write("\n\n" + block + "\n")
                learned += 1
        except Exception as e:
            print("[agent] one training msg failed:", e)
    QUEUE_FILE.write_text("[]", encoding="utf-8")   # clear the queue
    if learned and (chat := C.TG_CHAT):
        tg.send_text(f"📚 Learned {learned} new style example(s) from what you sent.", chat_id=chat)
    return learned

def maintain():
    """Cron entry (every ~15 min): drain training queue + enforce the auto-post deadline."""
    learned = _drain_queue()
    p = pending.load()
    if p and pending.expired(p):
        _publish(p, f"no response in {p.get('deadline_min',120)//60}h")
    print(f"[agent] maintain: learned={learned}, pending={'yes' if pending.is_pending() else 'no'}")

if __name__ == "__main__":
    maintain()

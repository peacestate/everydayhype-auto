"""GitHub-side helper for the Telegram WEBHOOK architecture.

The Cloudflare Worker (worker/worker.js) is the instant Telegram brain — it owns all live Telegram
updates and handles taps/edits in ~1s. This module does the heavy / scheduled work GitHub is better
at, and NEVER calls getUpdates (the webhook owns that now):

  • publish_approved() — dispatched (publish.yml) the instant you tap ✅: posts the approved carousel
                         to Instagram, records the ledger, confirms back.
  • maintain()         — cron (every ~15 min): drains training messages the Worker stashed in
                         state/tg_queue.json into examples.md, and AUTO-POSTS a pending post once it
                         passes the deadline (the "almost 2 hours" safety net)."""
import json, datetime
import config as C
from steps import ingest, telegram as tg, pending, s6_publish, s2_brain

QUEUE_FILE = C.STATE / "tg_queue.json"

# noon IST = 06:30 UTC. The Cloudflare Worker's 06:30-UTC cron is the PUNCTUAL primary publisher;
# this */15 cron is only a BACKUP — it publishes an approved post a touch later (>= 06:45 UTC /
# 12:15 IST) so it never races the worker's noon run, and it also catches approvals made after noon.
NOON_BACKUP_UTC_MIN = 6 * 60 + 45

def _utc_minutes_now():
    n = datetime.datetime.utcnow()
    return n.hour * 60 + n.minute

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
    """Cron entry (every ~15 min): drain training queue + BACKUP noon publisher.

    Posting is approval-gated now: nothing auto-posts on a timer. A post only goes out if you tap
    ✅ Approve, and then only at noon IST. The Cloudflare Worker's 06:30-UTC cron is the punctual
    primary publisher; this is the safety net (worker missed, or you approved after noon)."""
    learned = _drain_queue()
    p = pending.load()
    if p and p.get("status") == "approved" and _utc_minutes_now() >= NOON_BACKUP_UTC_MIN:
        _publish(p, "approved — noon post (backup)")
    print(f"[agent] maintain: learned={learned}, status={p and p.get('status')}")

if __name__ == "__main__":
    maintain()

"""The 'one post awaiting your decision' store (state/pending.json).

A real (non-dry-run) pipeline run no longer posts immediately — it renders, uploads the
slides to Cloudinary, and parks the post here as status='pending' with the Telegram control
message id. The Cloudflare Worker (worker/worker.js) owns the Telegram webhook and flips the
status on your Approve / Reject / edit; publish.yml then posts it.

Posting is APPROVAL-GATED: nothing is auto-posted on a timer. `deadline_min` and the
expired()/touch_deadline() helpers below are leftovers from the pre-2026-06-23 design, when an
untouched draft self-posted after 120 minutes. That behaviour was removed from agent.maintain()
— an approved post goes out at noon IST, and an unapproved one never goes out at all.

status: pending -> approved -> posting -> posted, or -> rejected. A failed post is reset to
'approved' so a later run can retry it.
"""
import json, datetime
import config as C

FILE = C.STATE / "pending.json"

def load():
    if not FILE.exists():
        return None
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

def save(d):
    FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")

def create(caption, image_urls, plan, chat_id, control_msg_id, deadline_min=120):
    save({
        "status": "pending",
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "deadline_min": deadline_min,
        "caption": caption,
        "image_urls": image_urls,
        "plan": plan,
        "chat_id": chat_id,
        "control_msg_id": control_msg_id,
    })

def is_pending():
    p = load()
    return bool(p and p.get("status") == "pending")

def minutes_old(p):
    try:
        born = datetime.datetime.fromisoformat(p["created_at"].rstrip("Z"))
    except Exception:
        return 0.0
    return (datetime.datetime.utcnow() - born).total_seconds() / 60.0

def expired(p):
    return p.get("status") == "pending" and minutes_old(p) >= p.get("deadline_min", 120)

def mark(status):
    p = load()
    if p:
        p["status"] = status
        p["resolved_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        save(p)

def touch_deadline():
    """Reset the auto-post timer — called when you actively edit, so it won't fire mid-edit."""
    p = load()
    if p:
        p["created_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        save(p)

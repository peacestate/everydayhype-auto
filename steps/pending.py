"""The 'one post awaiting your decision' store (state/pending.json).

A real (non-dry-run) pipeline run no longer posts immediately — it renders, uploads the
slides to Cloudinary, and parks the post here as status='pending' with the Telegram control
message id. The agent (steps/agent.py, on a short cron) then watches Telegram for your
Approve / Reject / edit, and AUTO-POSTS once `deadline_min` minutes pass with no response.
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

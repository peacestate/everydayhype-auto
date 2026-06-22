"""Telegram agent — the single getUpdates reader (Telegram allows only one).

Runs on a short cron (every ~15 min, laptop off) and does THREE things in one pass:

  1. TRAIN  — any image / text / file you DM (when no post is awaiting you) is distilled into
              a reusable winning pattern and appended to examples.md  (steps/ingest._handle).
  2. DECIDE — button taps on a queued post:
                ✅ approve -> publish to Instagram now
                ❌ reject  -> discard, post nothing
                🔄 regen   -> discard + re-trigger the daily pipeline (fresh visuals)
              and free-text replies WHILE a post is pending are treated as EDIT instructions
              (e.g. "shorten the caption") — the caption is revised and re-previewed.
  3. AUTO   — if a queued post sits unanswered for >= deadline_min (default 120), it is
              auto-published so the channel never misses a day.

Telegram offset is tracked in state/tg_offset.txt so nothing is read twice."""
import json, requests
from openai import OpenAI
import config as C
from steps import ingest, telegram as tg, pending, s6_publish, s2_brain

OFFSET_FILE = C.STATE / "tg_offset.txt"

def _publish(p, reason):
    """Publish a pending post to Instagram, record the ledger, report back. Idempotent-ish:
    flips status to 'posting' first so a crash mid-publish won't silently re-queue."""
    pending.mark("posting")
    try:
        media_id = s6_publish.publish(p["image_urls"], p["caption"])
    except Exception as e:
        pending.mark("pending")  # leave it queued so a later run / manual fix can retry
        tg.send_text(f"❌ Instagram post FAILED ({reason}): {e}", chat_id=p.get("chat_id"))
        print(f"[agent] publish failed: {e}"); return
    s2_brain.commit_ledger(p["plan"])
    pending.mark("posted")
    if p.get("control_msg_id"):
        tg.edit_text(p["control_msg_id"], f"✅ POSTED to Instagram (id {media_id}) — {reason}",
                     chat_id=p.get("chat_id"), reply_markup={"inline_keyboard": []})
    tg.send_text(f"✅ Posted carousel {media_id} — {reason}.", chat_id=p.get("chat_id"))
    print(f"[agent] PUBLISHED {media_id} ({reason})")

def _edit_caption(p, instruction):
    """Apply a free-text change request to the caption via the LLM, then re-preview."""
    client = OpenAI(api_key=C.OPENAI_API_KEY)
    sys = ("You edit Instagram captions for @everydayhypehq. Apply the user's requested change to "
           "the caption. Keep it on-brand (short factual paragraphs, an engagement question, "
           "'Sources:' line, 8-12 hashtags) unless they ask otherwise. Return ONLY the revised caption.")
    r = client.chat.completions.create(model=C.OPENAI_MODEL, temperature=0.5, messages=[
        {"role": "system", "content": sys},
        {"role": "user", "content": f"CURRENT CAPTION:\n{p['caption']}\n\nCHANGE REQUESTED:\n{instruction}"}])
    p["caption"] = r.choices[0].message.content.strip()
    pending.save(p)
    pending.touch_deadline()                       # active editing -> restart the auto-post timer
    if p.get("control_msg_id"):
        body = ("📝 Updated caption:\n" + p["caption"][:3500] +
                "\n\n⏳ Timer reset. Tap ✅ to post, ❌ to cancel, 🔄 to redo visuals, "
                "or reply with another change.")
        tg.edit_text(p["control_msg_id"], body, chat_id=p.get("chat_id"), reply_markup=tg.APPROVE_KB)
    print("[agent] caption edited per user instruction")

def _redispatch(p, status, working_msg, ok_msg):
    """Discard the queued post and re-trigger the daily pipeline (needs GH_PAT). Used by both
    🔄 Redo and ✨ Improve — the daily run always runs the auto-improve loop toward IMPROVE_TARGET."""
    pending.mark(status)
    if p.get("control_msg_id"):
        tg.edit_text(p["control_msg_id"], working_msg,
                     chat_id=p.get("chat_id"), reply_markup={"inline_keyboard": []})
    if not (C.GH_PAT and C.GH_REPO):
        tg.send_text("…but auto-redispatch isn't configured (no GH_PAT secret). "
                     "I'll produce a fresh, score-optimized carousel on the next daily run.",
                     chat_id=p.get("chat_id"))
        print(f"[agent] {status} requested but GH_PAT/GH_REPO unset"); return
    r = requests.post(f"https://api.github.com/repos/{C.GH_REPO}/actions/workflows/daily.yml/dispatches",
                      headers={"Authorization": f"Bearer {C.GH_PAT}",
                               "Accept": "application/vnd.github+json"},
                      json={"ref": "main", "inputs": {"dry_run": False}}, timeout=30)
    if r.status_code in (201, 204):
        tg.send_text(ok_msg, chat_id=p.get("chat_id"))
    else:
        tg.send_text(f"Couldn't auto-trigger (HTTP {r.status_code}). Run the daily workflow manually.",
                     chat_id=p.get("chat_id"))
    print(f"[agent] {status} dispatch -> {r.status_code}")

def _handle_callback(cb):
    data = cb.get("data")
    tg.answer_callback(cb["id"])
    p = pending.load()
    if not p or p.get("status") != "pending":
        tg.answer_callback(cb["id"], "Nothing pending — already handled."); return
    if data == "approve":
        _publish(p, "you approved")
    elif data == "reject":
        pending.mark("rejected")
        if p.get("control_msg_id"):
            tg.edit_text(p["control_msg_id"], "❌ Rejected — nothing posted.",
                         chat_id=p.get("chat_id"), reply_markup={"inline_keyboard": []})
    elif data == "improve":
        _redispatch(p, "improve", "✨ Pushing for a higher score — rebuilding & re-reviewing…",
                    "✨ Improving — a higher-scored carousel will arrive shortly.")
    elif data == "regen":
        _redispatch(p, "regen", "🔄 Discarded — regenerating a fresh carousel…",
                    "🔄 Regenerating — a new carousel will arrive shortly.")

def run():
    if not C.TG_TOKEN:
        print("[agent] no telegram token"); return
    offset = int(OFFSET_FILE.read_text().strip()) if OFFSET_FILE.exists() else 0
    updates = tg.api("getUpdates", offset=offset,
                     allowed_updates=json.dumps(["message", "callback_query"])).json().get("result", [])
    last, learned = offset, 0
    for u in updates:
        last = u["update_id"] + 1
        try:
            if "callback_query" in u:
                _handle_callback(u["callback_query"]); continue
            msg = u.get("message", {})
            chat = (msg.get("chat") or {}).get("id")
            p = pending.load()
            is_text = bool((msg.get("text") or "").strip()) and not msg.get("photo") and not msg.get("document")
            cmd = (msg.get("text") or "").strip().startswith("/")
            if p and p.get("status") == "pending" and is_text and not cmd:
                _edit_caption(p, msg["text"].strip())          # reply = edit the queued post
            else:
                block = ingest._handle(msg)                    # otherwise = training example
                if block:
                    with open(ingest.EXAMPLES, "a", encoding="utf-8") as f:
                        f.write("\n\n" + block + "\n")
                    learned += 1
                    if chat:
                        tg.send_text("✅ Learned from that — added to the library.", chat_id=chat)
        except Exception as e:
            print("[agent] one update failed:", e)
    if last != offset:
        OFFSET_FILE.write_text(str(last))

    # auto-post deadline
    p = pending.load()
    if p and pending.expired(p):
        _publish(p, f"no response in {p.get('deadline_min',120)//60}h")

    print(f"[agent] {len(updates)} updates, {learned} examples learned, "
          f"pending={'yes' if pending.is_pending() else 'no'}")

if __name__ == "__main__":
    run()

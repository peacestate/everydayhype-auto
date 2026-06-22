"""Telegram bridge for the everydayhypehq pipeline.

Two jobs:
  • notify()           — one-way preview (used by --dry-run): DMs the 5 slides + caption.
  • send_for_approval()— queue a real post: DMs the slides + a CONTROL message carrying
                         ✅ Approve / ❌ Reject / 🔄 Redo buttons. Returns the control
                         message id so the agent can edit it after a decision.
Plus low-level helpers the agent uses to answer button taps and report results.
Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (GitHub secrets). Graceful no-op if unset.
Note: Telegram media groups cannot carry inline keyboards, so buttons always live on a
separate text message sent right after the slides."""
import json, requests
import config as C

BASE = f"https://api.telegram.org/bot{C.TG_TOKEN}"

APPROVE_KB = {"inline_keyboard": [
    [{"text": "✅ Approve & Post", "callback_data": "approve"},
     {"text": "❌ Reject",         "callback_data": "reject"}],
    [{"text": "🔄 Redo visuals",   "callback_data": "regen"}],
]}

def _check(resp, what):
    # Telegram returns HTTP 200 {"ok":true,...}; failures are 4xx {"ok":false,"description":...}.
    # requests does NOT raise on 4xx, so failures otherwise look like successes — inspect the body.
    try:
        j = resp.json()
    except Exception:
        print(f"[tg] {what}: non-JSON reply (HTTP {resp.status_code})"); return None
    if not j.get("ok"):
        print(f"[tg] {what} FAILED: HTTP {resp.status_code} "
              f"error {j.get('error_code')} — {j.get('description')}")
        return None
    return j.get("result")

def api(method, **data):
    return requests.post(f"{BASE}/{method}", data=data, timeout=60)

def send_text(text, chat_id=None, reply_markup=None):
    data = {"chat_id": chat_id or C.TG_CHAT, "text": text[:4096]}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return _check(api("sendMessage", **data), "sendMessage")

def edit_text(message_id, text, chat_id=None, reply_markup=None):
    data = {"chat_id": chat_id or C.TG_CHAT, "message_id": message_id, "text": text[:4096]}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    return _check(api("editMessageText", **data), "editMessageText")

def answer_callback(callback_id, text=""):
    return api("answerCallbackQuery", callback_query_id=callback_id, text=text[:200])

def _send_slides(slide_paths, head_caption=None):
    if not slide_paths:
        return False
    files, media = {}, []
    for i, p in enumerate(slide_paths):
        files[f"f{i}"] = open(p, "rb")
        m = {"type": "photo", "media": f"attach://f{i}"}
        if i == 0 and head_caption:
            m["caption"] = head_caption[:1024]
        media.append(m)
    return _check(requests.post(f"{BASE}/sendMediaGroup",
                  data={"chat_id": C.TG_CHAT, "media": json.dumps(media)},
                  files=files, timeout=120), "sendMediaGroup") is not None

def _head(verdict, posted_id=None):
    v = verdict or {}
    h = ("🗞️ everydayhypehq — today's carousel\n"
         f"🎨 art-director: {v.get('verdict','?')} (score {v.get('score','?')})\n")
    if v.get("issues"):
        h += "⚠️ " + "; ".join(str(i) for i in v["issues"][:4]) + "\n"
    return h

def notify(slide_paths, caption, verdict, posted_id=None):
    """One-way preview (dry-run / quality-gate-skip messages)."""
    if not C.TG_TOKEN or not C.TG_CHAT:
        print("[tg] no telegram creds set — skipping"); return
    head = _head(verdict) + (f"✅ POSTED (id {posted_id})" if posted_id else "🕒 preview — not posted yet")
    ok = _send_slides(slide_paths, head)
    ok = (send_text("📝 Caption:\n" + (caption or "")) is not None) and ok
    print("[tg] sent today's carousel to Telegram" if ok else
          "[tg] ⚠️ Telegram did NOT deliver — see error(s) above. Common fix: send /start to your "
          "bot, and verify TELEGRAM_CHAT_ID is the numeric chat id (use tools/tg_check.py).")

def send_for_approval(slide_paths, caption, verdict, deadline_min=120):
    """Queue a real post for your decision. Returns (chat_id, control_msg_id) or (None, None)."""
    if not C.TG_TOKEN or not C.TG_CHAT:
        print("[tg] no telegram creds set — cannot queue for approval"); return None, None
    _send_slides(slide_paths, _head(verdict) + "🕒 awaiting your decision")
    body = ("📝 Caption:\n" + (caption or "") +
            f"\n\n⏳ Auto-posts in ~{deadline_min//60}h if you don't respond.\n"
            "• Tap ✅ to post now, ❌ to cancel, 🔄 to regenerate the visuals.\n"
            "• Or just reply with a change (e.g. \"shorten the caption\", \"make it punchier\", "
            "\"add a question at the end\") and I'll revise it.")
    res = send_text(body, reply_markup=APPROVE_KB)
    if not res:
        print("[tg] ⚠️ could not send approval message — see error above"); return None, None
    return res["chat"]["id"], res["message_id"]

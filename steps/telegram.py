"""Telegram daily preview — DMs today's rendered carousel (5 slides) + caption + art-director
verdict to your Telegram, so you see what the pipeline made even with your laptop off.
Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (GitHub secrets). Graceful no-op if unset."""
import json, requests
import config as C

def notify(slide_paths, caption, verdict, posted_id=None):
    if not C.TG_TOKEN or not C.TG_CHAT:
        print("[tg] no telegram creds set — skipping"); return
    base = f"https://api.telegram.org/bot{C.TG_TOKEN}"
    v = verdict or {}
    head = ("🗞️ everydayhypehq — today's carousel\n"
            f"🎨 art-director: {v.get('verdict','?')} (score {v.get('score','?')})\n")
    if v.get("issues"):
        head += "⚠️ " + "; ".join(str(i) for i in v["issues"][:4]) + "\n"
    head += (f"✅ POSTED (id {posted_id})" if posted_id else "🕒 preview — not posted yet")
    def _check(resp, what):
        # Telegram returns HTTP 200 with {"ok":true,...}; on failure it's a 4xx with
        # {"ok":false,"error_code":N,"description":"..."}. requests.post does NOT raise
        # on 4xx, so we must inspect the body or failures look like successes.
        try:
            j = resp.json()
        except Exception:
            print(f"[tg] {what}: non-JSON reply (HTTP {resp.status_code})"); return False
        if not j.get("ok"):
            print(f"[tg] {what} FAILED: HTTP {resp.status_code} "
                  f"error {j.get('error_code')} — {j.get('description')}")
            return False
        return True

    try:
        files, media = {}, []
        for i, p in enumerate(slide_paths):
            files[f"f{i}"] = open(p, "rb")
            m = {"type": "photo", "media": f"attach://f{i}"}
            if i == 0:
                m["caption"] = head[:1024]
            media.append(m)
        ok = _check(requests.post(f"{base}/sendMediaGroup",
                      data={"chat_id": C.TG_CHAT, "media": json.dumps(media)},
                      files=files, timeout=90), "sendMediaGroup")
        ok &= _check(requests.post(f"{base}/sendMessage",
                      data={"chat_id": C.TG_CHAT, "text": ("📝 Caption:\n" + (caption or ""))[:4096]},
                      timeout=30), "sendMessage")
        if ok:
            print("[tg] sent today's carousel to Telegram")
        else:
            print("[tg] ⚠️ Telegram did NOT deliver — see error(s) above. "
                  "Common fix: send /start to your bot, and verify TELEGRAM_CHAT_ID "
                  "is the numeric chat id (use getUpdates).")
    except Exception as e:
        print(f"[tg] send failed (non-fatal): {e}")

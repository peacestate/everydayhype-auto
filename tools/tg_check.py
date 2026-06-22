"""Telegram delivery diagnostic for the daily-carousel pipeline.

Usage (PowerShell / bash):
    TELEGRAM_BOT_TOKEN=123:ABC TELEGRAM_CHAT_ID=999 python tools/tg_check.py
    # or with a test message:
    ... python tools/tg_check.py --send

What it does:
  1. getMe        -> proves the BOT TOKEN is valid (prints the bot @username).
  2. getUpdates   -> lists every chat that has messaged the bot, with the numeric
                     chat.id you should put in TELEGRAM_CHAT_ID. (You must have sent
                     /start or any message to the bot for it to appear here.)
  3. --send       -> actually sends a "pipeline test" message to TELEGRAM_CHAT_ID and
                     reports Telegram's real ok/error (the thing the pipeline hid before).
"""
import os, sys, requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE  = f"https://api.telegram.org/bot{TOKEN}"

def die(msg): print(msg); sys.exit(1)

if not TOKEN:
    die("✗ TELEGRAM_BOT_TOKEN not set in env.")

# 1) token valid?
me = requests.get(f"{BASE}/getMe", timeout=20).json()
if not me.get("ok"):
    die(f"✗ getMe failed — token is wrong/revoked: {me.get('description')}")
print(f"✓ token OK — bot is @{me['result'].get('username')} (id {me['result'].get('id')})")

# 2) who has talked to the bot? -> the chat id(s) you can use
up = requests.get(f"{BASE}/getUpdates", timeout=20).json()
seen = {}
for u in up.get("result", []):
    chat = (u.get("message") or u.get("channel_post") or {}).get("chat") or {}
    if chat.get("id") is not None:
        who = chat.get("title") or chat.get("username") or chat.get("first_name") or "?"
        seen[chat["id"]] = f"{chat.get('type')} '{who}'"
if seen:
    print("✓ chats that have messaged this bot (use one of these ids):")
    for cid, desc in seen.items():
        mark = "  <-- matches TELEGRAM_CHAT_ID" if str(cid) == str(CHAT) else ""
        print(f"    {cid}   {desc}{mark}")
    if CHAT and str(CHAT) not in map(str, seen):
        print(f"✗ your TELEGRAM_CHAT_ID={CHAT} is NOT in the list above — wrong id.")
else:
    print("✗ getUpdates is empty — NO ONE has messaged this bot yet.")
    print("  Fix: open Telegram, find the bot above, press Start (send /start), then re-run.")

# 3) optional live send
if "--send" in sys.argv:
    if not CHAT:
        die("✗ TELEGRAM_CHAT_ID not set — cannot test send.")
    r = requests.post(f"{BASE}/sendMessage",
                      data={"chat_id": CHAT, "text": "✅ everydayhype pipeline — Telegram test OK"},
                      timeout=20).json()
    if r.get("ok"):
        print(f"✓ test message delivered to chat {CHAT}")
    else:
        print(f"✗ send FAILED: error {r.get('error_code')} — {r.get('description')}")

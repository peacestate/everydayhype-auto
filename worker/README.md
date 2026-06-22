# Instant Telegram bot — Cloudflare Worker (one-time setup)

This makes your bot's buttons respond in ~1 second instead of waiting ~15 min. It's **free** and
needs **no credit card**. Do this once.

## 0. What you need
- A free **Cloudflare** account → https://dash.cloudflare.com/sign-up
- **Node.js** installed (https://nodejs.org) — gives you `npm`
- Your **GH_PAT** token (fine-grained, repo `everydayhype-auto`, permissions **Contents: Read/write**
  AND **Actions: Read/write**). Create at https://github.com/settings/personal-access-tokens/new

## 1. Install Wrangler (Cloudflare's CLI) and log in
```bash
npm install -g wrangler
wrangler login          # opens a browser, click Allow
```

## 2. Deploy the worker
From this `worker/` folder:
```bash
wrangler deploy
```
Copy the URL it prints, e.g. `https://everydayhype-bot.<you>.workers.dev`.

## 3. Add the secrets (paste each value when prompted)
```bash
wrangler secret put TELEGRAM_BOT_TOKEN     # from @BotFather
wrangler secret put TELEGRAM_CHAT_ID       # your numeric chat id
wrangler secret put OPENAI_API_KEY
wrangler secret put GH_PAT                 # the fine-grained token above
wrangler secret put GH_REPO                # type:  kiAnukal/everydayhype-auto
wrangler secret put WEBHOOK_SECRET         # invent any long random string, remember it
```
Then redeploy so the secrets load: `wrangler deploy`

## 4. Point Telegram at the worker (the "webhook")
Replace the 3 ALL-CAPS values and run once (curl or in a browser):
```bash
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=YOUR_WORKER_URL&secret_token=YOUR_WEBHOOK_SECRET&allowed_updates=[%22message%22,%22callback_query%22]"
```
You should see `{"ok":true,"result":true,...}`. Done — taps are now instant.

### Check / undo
- Check: `https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo`
- Undo (go back to the slow GitHub polling): `https://api.telegram.org/botYOUR_BOT_TOKEN/deleteWebhook`

## How it fits together
- **Cloudflare Worker** = instant brain. Handles every tap/reply live: ✅ approve, ❌ reject,
  ✨ improve, 🔄 redo, and caption edits. Updates `state/pending.json` via the GitHub API.
- **GitHub Actions** still does the heavy work: `daily.yml` builds + auto-improves the carousel and
  queues it; `publish.yml` posts the approved one to Instagram (dispatched by the Worker on ✅);
  `telegram-maintain` (cron) drains training messages into `examples.md` and auto-posts after ~2h.
- ⚠️ A webhook and the old polling can't both run. Once the webhook is set, Telegram stops answering
  `getUpdates`, which is fine — `telegram-maintain` no longer uses it.

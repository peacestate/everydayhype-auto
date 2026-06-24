/**
 * everydayhypehq — instant Telegram brain (Cloudflare Worker).
 *
 * Telegram pushes every tap/message here via webhook, so responses are INSTANT (~1s) instead of
 * waiting for the 15-min GitHub poll. The Worker is lightweight: it acknowledges instantly, updates
 * the queued-post state (state/pending.json in the repo, via the GitHub API), and hands the heavy /
 * slow work to GitHub Actions:
 *   ✅ approve  -> mark pending 'approved' (does NOT post now — the 12:00 PM IST cron posts it)
 *   ❌ reject   -> mark pending 'rejected'  (done — nothing posts)
 *   ✨ improve / 🔄 regen -> dispatch daily.yml for a fresh, score-optimized carousel
 *   text reply while a post is pending -> revise the caption via OpenAI + re-show it
 *   any other message (image/file/idea) -> stash to state/tg_queue.json for the training drainer
 *
 * Secrets (wrangler secret put / dashboard): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OPENAI_API_KEY,
 * GH_PAT (repo contents:write + actions:write), GH_REPO (owner/name), WEBHOOK_SECRET.
 */

const GH_API = "https://api.github.com";

export default {
  async fetch(req, env) {
    if (req.method !== "POST") return new Response("ok"); // health check / browser hit
    // Telegram sends our shared secret in this header — reject anything else.
    if (env.WEBHOOK_SECRET &&
        req.headers.get("x-telegram-bot-api-secret-token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    let update;
    try { update = await req.json(); } catch { return new Response("bad json", { status: 400 }); }
    try {
      if (update.callback_query) await handleCallback(update.callback_query, env);
      else if (update.message)   await handleMessage(update.message, env);
    } catch (e) {
      console.log("worker error:", e && e.stack || e);
    }
    return new Response("ok"); // always 200 so Telegram doesn't retry-storm
  },

  /**
   * Cron triggers (see wrangler.toml [triggers]). Cloudflare fires these on the dot and we turn
   * each into a GitHub workflow_dispatch — dispatched runs start promptly, so we hit real clock
   * times that GitHub's own (heavily delayed) schedule cron never could.
   *   03:40 UTC / 09:10 IST -> daily.yml   -> builds + DMs the draft (lands ~09:30 IST)
   *   06:30 UTC / 12:00 IST -> publish.yml -> posts the carousel IF you've approved it
   */
  async scheduled(event, env, ctx) {
    try {
      if (event.cron === "40 3 * * *") {
        const ok = await ghDispatch(env, "daily.yml", { dry_run: "false" });
        console.log("cron 09:10 IST -> daily.yml dispatch:", ok);
      } else if (event.cron === "30 6 * * *") {
        // publish.yml's publish_approved() no-ops unless pending.json status === 'approved',
        // so firing this at noon is safe whether or not you approved.
        const ok = await ghDispatch(env, "publish.yml", {});
        console.log("cron 12:00 IST -> publish.yml dispatch:", ok);
        // courtesy heads-up if nothing was approved in time
        try {
          const { obj: p } = await ghGetFile(env, "state/pending.json");
          if (p && p.status !== "approved" && p.status !== "posted" && p.status !== "posting") {
            await sendText(env, env.TELEGRAM_CHAT_ID,
              "🕛 It's 12:00 PM IST — no carousel was approved, so nothing is posting today. Tap ✅ on a draft before noon to schedule it.");
          }
        } catch {}
      }
    } catch (e) {
      console.log("scheduled error:", e && e.stack || e);
    }
  },
};

/* ---------------- Telegram helpers ---------------- */
const tgBase = (env) => `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}`;
async function tg(env, method, body) {
  const r = await fetch(`${tgBase(env)}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  return r.json();
}
const answerCb = (env, id, text) => tg(env, "answerCallbackQuery", { callback_query_id: id, text: (text || "").slice(0, 200) });
const sendText = (env, chat, text, kb) => tg(env, "sendMessage", { chat_id: chat, text: text.slice(0, 4096), ...(kb ? { reply_markup: kb } : {}) });
const editText = (env, chat, mid, text, kb) => tg(env, "editMessageText", { chat_id: chat, message_id: mid, text: text.slice(0, 4096), reply_markup: kb || { inline_keyboard: [] } });

const KB = {
  inline_keyboard: [
    [{ text: "✅ Approve (post at noon)", callback_data: "approve" }, { text: "❌ Reject", callback_data: "reject" }],
    [{ text: "✨ Improve to 100", callback_data: "improve" }, { text: "🔄 Redo visuals", callback_data: "regen" }],
    [{ text: "🧊 Isometric 3D", callback_data: "style_iso" }, { text: "💎 Glossy 3D", callback_data: "style_glossy" }],
  ],
};

/* ---------------- GitHub helpers ---------------- */
function ghHeaders(env) {
  return { Authorization: `Bearer ${env.GH_PAT}`, Accept: "application/vnd.github+json", "User-Agent": "everydayhype-worker" };
}
async function ghGetFile(env, path) {
  const r = await fetch(`${GH_API}/repos/${env.GH_REPO}/contents/${path}`, { headers: ghHeaders(env) });
  if (r.status === 404) return { obj: null, sha: null };
  const j = await r.json();
  const text = decodeURIComponent(escape(atob(j.content.replace(/\n/g, ""))));
  return { obj: JSON.parse(text), sha: j.sha };
}
async function ghPutFile(env, path, obj, sha, message) {
  const content = btoa(unescape(encodeURIComponent(JSON.stringify(obj, null, 2))));
  const r = await fetch(`${GH_API}/repos/${env.GH_REPO}/contents/${path}`, {
    method: "PUT", headers: { ...ghHeaders(env), "content-type": "application/json" },
    body: JSON.stringify({ message, content, ...(sha ? { sha } : {}) }),
  });
  return r.ok;
}
async function ghDispatch(env, workflow, inputs) {
  const r = await fetch(`${GH_API}/repos/${env.GH_REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST", headers: { ...ghHeaders(env), "content-type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: inputs || {} }),
  });
  return r.status === 204 || r.status === 201;
}

/* ---------------- button taps (INSTANT) ---------------- */
async function handleCallback(cb, env) {
  const chat = cb.message?.chat?.id || env.TELEGRAM_CHAT_ID;
  const mid = cb.message?.message_id;
  const data = cb.data;
  await answerCb(env, cb.id, "Got it…");

  const { obj: p, sha } = await ghGetFile(env, "state/pending.json");
  if (!p || p.status !== "pending") {
    if (mid) await editText(env, chat, mid, "ℹ️ This post was already handled.");
    return;
  }

  if (data === "reject") {
    p.status = "rejected"; p.resolved_at = new Date().toISOString();
    await ghPutFile(env, "state/pending.json", p, sha, "reject via telegram (worker)");
    if (mid) await editText(env, chat, mid, "❌ Rejected — nothing will be posted.");
    return;
  }
  if (data === "approve") {
    p.status = "approved"; p.resolved_at = new Date().toISOString();
    await ghPutFile(env, "state/pending.json", p, sha, "approve via telegram (worker)");
    // DON'T post now — approval just schedules it. The 12:00 PM IST cron (and a */15 backup)
    // publishes the approved carousel, regardless of what time you approved.
    if (mid) await editText(env, chat, mid, "✅ Approved — scheduled to post at 12:00 PM IST.");
    return;
  }
  // 🔄 redo visuals (fresh rotation) · ✨ improve · 🧊/💎 redo in a forced 3D style
  if (data === "improve" || data === "regen" || data === "style_iso" || data === "style_glossy") {
    const force = data === "style_iso" ? "iso" : data === "style_glossy" ? "glossy" : "";
    const ok = await ghDispatch(env, "daily.yml", { dry_run: "false", force_style: force });
    if (ok) {
      p.status = data; await ghPutFile(env, "state/pending.json", p, sha, `${data} via telegram (worker)`);
      const msg = data === "improve"  ? "✨ Rebuilding for a higher score — a new carousel will arrive shortly."
                : data === "style_iso"    ? "🧊 Regenerating in isometric 3D diorama — a fresh carousel will arrive shortly."
                : data === "style_glossy" ? "💎 Regenerating in glossy 3D render — a fresh carousel will arrive shortly."
                : "🔄 Regenerating — a fresh carousel will arrive shortly.";
      if (mid) await editText(env, chat, mid, msg);
    } else if (mid) {
      await editText(env, chat, mid, "⚠️ Couldn't start a new run (check GH_PAT). Your post is still here to approve.", KB);
    }
    return;
  }
}

/* ---------------- messages (edits + training) ---------------- */
async function handleMessage(msg, env) {
  const chat = msg.chat?.id || env.TELEGRAM_CHAT_ID;
  const text = (msg.text || msg.caption || "").trim();
  const isPlainText = text && !msg.photo && !msg.document;
  const isCmd = text.startsWith("/");

  const { obj: p, sha } = await ghGetFile(env, "state/pending.json");
  const pending = p && p.status === "pending";

  // a text reply WHILE a post is pending = "edit the caption like this"
  if (pending && isPlainText && !isCmd) {
    const newCap = await reviseCaption(env, p.caption, text);
    if (newCap) {
      p.caption = newCap; p.created_at = new Date().toISOString(); // reset the auto-post timer
      await ghPutFile(env, "state/pending.json", p, sha, "caption edit via telegram (worker)");
      await sendText(env, chat, "📝 Updated caption:\n\n" + newCap.slice(0, 3500) +
        "\n\n✅ post · ❌ cancel · ✨ improve · 🔄 redo — or reply with another change.", KB);
    } else {
      await sendText(env, chat, "⚠️ Couldn't revise that — try rewording the change.");
    }
    return;
  }
  // /draftcarousel — build a carousel RIGHT NOW, regardless of the daily schedule.
  // Optional style arg: "/draftcarousel iso" or "/draftcarousel glossy" forces a 3D look.
  if (/^\/draft(carousel)?\b/i.test(text)) {
    const arg = text.split(/\s+/)[1]?.toLowerCase() || "";
    const force = arg === "iso" || arg === "glossy" ? arg : "";
    const ok = await ghDispatch(env, "daily.yml", { dry_run: "false", force_style: force });
    await sendText(env, chat, ok
      ? `🛠️ Building a fresh carousel now${force ? ` in ${force === "iso" ? "isometric 3D" : "glossy 3D"}` : ""} — it'll arrive in a few minutes with the approve buttons.`
      : "⚠️ Couldn't start a run (check GH_PAT).");
    return;
  }
  if (isCmd) { await sendText(env, chat, "👋 Send me a top-post screenshot, an idea, or an Apify export and I'll learn its style. When a carousel is waiting, tap the buttons or reply to edit it.\n\nTip: /draftcarousel builds one now (add `iso` or `glossy` for a 3D look)."); return; }

  // otherwise it's a TRAINING example -> stash for the GitHub drainer (heavy parsing stays in Python)
  const { obj: q, sha: qsha } = await ghGetFile(env, "state/tg_queue.json");
  const queue = Array.isArray(q) ? q : [];
  queue.push(msg);
  const ok = await ghPutFile(env, "state/tg_queue.json", queue, qsha, "queue telegram training msg (worker)");
  await sendText(env, chat, ok ? "✅ Got it — I'll learn its style on the next pass."
                               : "⚠️ Couldn't save that one, try again.");
}

async function reviseCaption(env, current, instruction) {
  const sys = "You edit Instagram captions for @everydayhypehq. Apply the user's change to the caption, " +
    "keeping it on-brand (short factual paragraphs, an engagement question, 'Sources:' line, 8-12 hashtags) " +
    "unless they ask otherwise. Return ONLY the revised caption.";
  const r = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST", headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({
      model: "gpt-4o-mini", temperature: 0.5,
      messages: [{ role: "system", content: sys },
                 { role: "user", content: `CURRENT CAPTION:\n${current}\n\nCHANGE REQUESTED:\n${instruction}` }],
    }),
  });
  if (!r.ok) return null;
  const j = await r.json();
  return j.choices?.[0]?.message?.content?.trim() || null;
}

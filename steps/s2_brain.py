"""Step 2 — the BRAIN (OpenAI), now FACT-GROUNDED.
(1) pick the best AI/tech story, (2) FETCH the actual article text, (3) write copy built from real
facts (numbers/names/dates) with hard anti-fluff rules, + plan varied palette/style/layout.
Returns a plan dict or None (skip day)."""
import json, datetime, re, urllib.request
from openai import OpenAI
import config as C

LEDGER = C.STATE / "style_ledger.json"
HISTORY = C.STATE / "posted_history.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; everydayhypehq-bot/1.0)"}

def _load(p, default): return json.loads(p.read_text()) if p.exists() else default
def _recent(ledger, key, days=C.AVOID_DAYS): return [e[key] for e in ledger[-days:] if key in e]

def _fetch_article(url, limit=3000):
    """Pull clean article text. Jina Reader (r.jina.ai) bypasses most bot-blocking; fall back to raw."""
    # 1) Jina Reader proxy -> clean markdown text
    try:
        txt = urllib.request.urlopen(urllib.request.Request("https://r.jina.ai/" + url, headers=UA), timeout=30).read().decode("utf-8", "replace")
        txt = re.sub(r"\s+", " ", txt).strip()
        if len(txt) > 400:
            return txt[:limit]
    except Exception as e:
        print("[s2] jina fetch failed:", e)
    # 2) raw fetch fallback
    try:
        html = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode("utf-8", "replace")
        html = re.sub(r"(?is)<(script|style|nav|header|footer|aside).*?</\1>", " ", html)
        paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
        text = re.sub(r"\s+", " ", " ".join(re.sub(r"(?is)<[^>]+>", " ", p) for p in paras)).strip()
        return text[:limit]
    except Exception as e:
        print("[s2] raw fetch failed:", e); return ""

PICK_SYS = """You are the editor of @everydayhypehq (AI/tech news). From the candidate headlines, pick the
ONE best story: must be about AI or frontier tech (new models/products, robotics, chips, big AI moves,
breakthroughs, AI safety/security), genuinely trending, recent, real — NOT generic politics/finance or
meta-discussion. Avoid anything similar to already_posted. If nothing qualifies, skip. Return JSON:
{"skip":bool,"confidence":0-100,"index":int (into candidates),"why":""}"""

WRITE_SYS = """You are the editor + art director for @everydayhypehq. Write a 5-slide carousel that is
SPECIFIC and FACTUAL, built from the ARTICLE text provided — never generic.
HARD RULES:
- EVERY slide must contain a CONCRETE specific pulled from the article: a number, %, name, company,
  date, or hard fact. If the article gives stats, USE them.
- NAME THE PROTAGONIST: identify the main actor of the story (the company, lab, person, or product
  that DID the thing) and name them EXPLICITLY on slide 1 AND in the caption — e.g. "OPENAI", "GOOGLE
  DEEPMIND", a named researcher or product. A reader must know WHO this is about from the first slide.
  Do NOT bury or omit the protagonist. NEVER let an unrelated competitor be the only company named, and
  only mention a rival company if the article does AND the protagonist is named more prominently.
- NEVER FABRICATE. Only use numbers/names/dates/facts that LITERALLY appear in article_text. If the
  article is empty or sparse, write truthfully from the headline and stay factual — do NOT invent any
  statistic, percentage, or detail. A true-but-general line beats a made-up specific.
- BANNED (do not write these): "revolutionizing", "game-changer", "the future is here", "in record
  time", "changing everything", "mind-blowing", "you won't believe", "proactive", "cutting-edge",
  "next-level", "transforming", "unlocking potential", "the power of AI". No empty hype.
- Slide 1 = the single most SHOCKING concrete fact as the hook (think: "AI READ 2M LINES OF CODE AND
  FOUND THE BUG IN 4 MINUTES"). Slides 2-4 = specific details/numbers/names. Slide 5 = takeaway that
  states the SIGNIFICANCE with a concrete fact or sharp implication (e.g. "AND IT RUNS ON ONE GPU",
  "AT 1/10TH THE COST") + the follow CTA. The banned-words rule applies to ALL 5 slides AND the caption.
- Headlines SHORT, UPPERCASE-ready, each with 1-2 highlight words ('hl', a substring of the headline).
- The 'sub' line is a FULL supporting sentence of 8-14 words that adds a SECOND concrete fact, name,
  number, date, or consequence from the article — a complete thought that stands on its own. NEVER a
  2-4 word fragment or trailing tail (BAD: "on board" / "every major OS" / "since 1999"; GOOD:
  "Apple, Google and JPMorgan have already deployed the scanner across their systems").
- Caption = 1-2 punchy sentences with the KEY fact + 8-12 relevant hashtags. No fluff.
- 5 image prompts, each a DISTINCT subject (never repeat a motif), >=1 human/people shot, cohesive with
  the chosen palette + art_style but tonally varied.
- CRITICAL: every image prompt MUST be a pure PHOTOGRAPHIC scene with NO readable elements. NEVER depict
  text, words, numbers, charts, graphs, stock tickers, dashboards, comparison tables, logos, brand marks,
  screens/monitors showing UI, signage, or labels — the image model renders these as garbled melted
  gibberish (and invents fake numbers). Instead describe people, faces, hands, hardware, places,
  objects, environments, lighting and mood. All real text/data belongs in the overlay, never in the image.
Return STRICT JSON matching the given schema."""

def make_plan(candidates):
    client = OpenAI(api_key=C.OPENAI_API_KEY)
    ledger, history = _load(LEDGER, []), _load(HISTORY, [])

    # STAGE 1 — pick the story (titles only)
    pick = json.loads(client.chat.completions.create(
        model=C.OPENAI_MODEL, response_format={"type": "json_object"}, temperature=0.4,
        messages=[{"role": "system", "content": PICK_SYS}, {"role": "user", "content": json.dumps({
            "candidates": [{"i": i, "title": c["title"], "src": c["src"], "score": c["score"]} for i, c in enumerate(candidates)],
            "already_posted": [h["title"] for h in history[-30:]]})}]).choices[0].message.content)
    if pick.get("skip") or pick.get("confidence", 0) < 60:
        print(f"[s2] skip day (confidence={pick.get('confidence')})"); return None
    story = candidates[int(pick["index"])]
    print(f"[s2] picked: {story['title']}")

    # STAGE 2 — fetch the real article
    article = _fetch_article(story["url"])
    print(f"[s2] article chars: {len(article)}")

    # STAGE 3 — write fact-grounded copy + varied visuals (with a deterministic anti-fluff guard)
    BANNED = ["revolutioniz", "game-chang", "game chang", "the future is here", "in record time",
              "changing everything", "mind-blow", "you won't believe", "proactive", "cutting-edge",
              "cutting edge", "next-level", "next level", "unlocking", "the power of ai", "groundbreaking",
              "seamless", "redefin", "stay tuned", "discover more", "the future of"]
    def _fluff(p):
        slides = p.get("slides") or []
        blob = (p.get("caption", "") + " " + " ".join(
            (s.get("headline", "") + " " + s.get("sub", "")) for s in slides if isinstance(s, dict))).lower()
        return [w for w in BANNED if w in blob]
    def _valid(p):
        s = p.get("slides")
        return isinstance(s, list) and len(s) == 5 and all(
            isinstance(x, dict) and x.get("headline") for x in s)
    def _thin(p):  # slide numbers whose 'sub' is a fragment, not a full supporting line
        return [i + 1 for i, x in enumerate(p.get("slides") or [])
                if isinstance(x, dict) and len(str(x.get("sub", "")).split()) < 7]
    user = {
        "story_title": story["title"], "story_url": story["url"], "article_text": article or "(article unavailable — use only the headline; still avoid all banned fluff words)",
        "avoid_recent_palettes": _recent(ledger, "palette"), "avoid_recent_art_styles": _recent(ledger, "art_style"),
        "avoid_recent_layouts": _recent(ledger, "layout"),
        "palette_pool": [p["name"] for p in C.PALETTES], "art_style_pool": C.ART_STYLES, "layout_pool": C.LAYOUTS, "pills": C.PILLS,
        "schema": {"palette": "name not in avoid", "art_style": "from pool not in avoid", "layout": "from pool not in avoid",
                   "caption": "", "slides": [{"pill": "", "headline": "", "hl": "", "sub": "", "image_prompt": ""}]}}
    msgs = [{"role": "system", "content": WRITE_SYS}, {"role": "user", "content": json.dumps(user)}]
    plan = None
    for attempt in range(3):
        plan = json.loads(client.chat.completions.create(
            model=C.OPENAI_MODEL, response_format={"type": "json_object"}, temperature=0.7,
            messages=msgs).choices[0].message.content)
        bad = _fluff(plan)
        thin = _thin(plan)
        if _valid(plan) and not bad and not thin:
            break
        problems = []
        if not _valid(plan):
            problems.append("return EXACTLY 5 slides as a JSON array, each an object with non-empty "
                            "'pill','headline','hl','sub','image_prompt' fields per the schema")
        if bad:
            problems.append(f"remove these BANNED fluff phrases {bad}, replacing each with a concrete "
                            "fact from the article or a sharp factual statement")
        if thin:
            problems.append(f"slides {thin} have a too-short 'sub' — rewrite each as a FULL 8-14 word "
                            "supporting sentence adding a second concrete fact, not a fragment or tail")
        print(f"[s2] guard retry (attempt {attempt+1}): valid={_valid(plan)} fluff={bad} thin={thin}")
        msgs.append({"role": "assistant", "content": json.dumps(plan)})
        msgs.append({"role": "user", "content": "REWRITE strictly as JSON, keeping the schema: " + "; ".join(problems) + "."})

    if not _valid(plan):
        raise ValueError(f"s2 brain returned malformed plan after retries (slides={type(plan.get('slides')).__name__})")
    # Sanitize LLM text: strip ANSI escape sequences + stray control chars (the model
    # has injected raw \x1b[31m into fields), so nothing garbled reaches slides or the IG caption.
    _ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    def _clean(x):
        if not isinstance(x, str): return x
        return "".join(c for c in _ANSI.sub("", x) if c >= " " or c in "\n\t").strip()
    plan["caption"] = _clean(plan.get("caption", ""))
    for sl in plan["slides"]:
        for k in ("pill", "headline", "hl", "sub", "image_prompt"):
            if k in sl:
                sl[k] = _clean(sl[k])
    plan["story"] = {"title": story["title"], "url": story["url"]}
    plan["date"] = datetime.date.today().isoformat()
    print(f'[s2] {plan["palette"]}/{plan["art_style"][:18]}/{plan["layout"]} | {plan["slides"][0]["headline"]}')
    return plan

def commit_ledger(plan):
    ledger, history = _load(LEDGER, []), _load(HISTORY, [])
    ledger.append({"date": plan["date"], "palette": plan["palette"], "art_style": plan["art_style"],
                   "layout": plan["layout"], "motifs": [s["image_prompt"][:40] for s in plan["slides"]]})
    history.append({"date": plan["date"], "title": plan["story"]["title"]})
    LEDGER.write_text(json.dumps(ledger[-60:], indent=2))
    HISTORY.write_text(json.dumps(history[-200:], indent=2))

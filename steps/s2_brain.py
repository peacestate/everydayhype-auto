"""Step 2 — the BRAIN (OpenAI). Ranks candidates, picks the best fresh story, plans a
varied palette/style/layout (avoiding recent days), and writes the 5-slide copy with
5 DISTINCT image prompts (no repeated motif, >=1 human shot). Returns a plan dict or None (skip day)."""
import json, datetime
from pathlib import Path
from openai import OpenAI
import config as C

LEDGER = C.STATE / "style_ledger.json"
HISTORY = C.STATE / "posted_history.json"

def _load(p, default): return json.loads(p.read_text()) if p.exists() else default

def _recent(ledger, key, days=C.AVOID_DAYS):
    return [e[key] for e in ledger[-days:] if key in e]

SYSTEM = """You are the editor + art director for @everydayhypehq, a bold AI/tech news Instagram
carousel brand. You write punchy, accurate, curiosity-driven copy and plan striking, VARIED visuals.
Rules you MUST follow:
- TOPIC: the story MUST be about AI or frontier tech — new AI models/products, robotics, chips,
  major tech-company AI moves, AI breakthroughs, AI safety/security. REJECT generic politics, energy,
  finance, or meta-discussion-about-AI unless it's a concrete AI development. If nothing qualifies, skip.
- Pick ONE story that is genuinely trending, recent, real. Reject clickbait/rumor; prefer a known outlet.
- HEADLINES must be BOLD and SHOCKING with a curiosity gap — concrete, specific, ideally with a number
  or a surprising claim. Slide 1 is the HOOK. GOOD: "SCIENTISTS JUST BUILT AN AI THAT CODES ITSELF",
  "THIS AI FOUND A 27-YEAR-OLD FLAW IN SECONDS". BAD/vague: "WHAT IT MEANS FOR US", "THE POWER OF AI".
- 5 slides, each headline SHORT + UPPERCASE-ready with 1-2 highlight words ('hl', a substring of headline).
- The 5 image prompts must each be a DISTINCT subject — NEVER repeat a motif (no padlock twice, etc.).
- Include at least ONE human/people shot. Vary scene types (object, environment, people, concept).
- Keep imagery cohesive with the chosen palette + art style, but tonally varied slide to slide.
Return STRICT JSON only."""

def make_plan(candidates):
    client = OpenAI(api_key=C.OPENAI_API_KEY)
    ledger  = _load(LEDGER, [])
    history = _load(HISTORY, [])
    avoid = {
        "palettes": _recent(ledger, "palette"),
        "art_styles": _recent(ledger, "art_style"),
        "layouts": _recent(ledger, "layout"),
        "past_titles": [h["title"] for h in history[-30:]],
    }
    user = {
        "candidates": [{"title": c["title"], "src": c["src"], "score": c["score"]} for c in candidates],
        "avoid_recent_palettes": avoid["palettes"],
        "avoid_recent_art_styles": avoid["art_styles"],
        "avoid_recent_layouts": avoid["layouts"],
        "already_posted_last_30d": avoid["past_titles"],
        "palette_pool": [p["name"] for p in C.PALETTES],
        "art_style_pool": C.ART_STYLES,
        "layout_pool": C.LAYOUTS,
        "pills": C.PILLS,
        "output_schema": {
            "skip": "bool (true if no candidate is strong/fresh enough -> we post nothing today)",
            "confidence": "0-100",
            "story": {"title": "", "url": "", "why_it_matters": ""},
            "palette": "one name from palette_pool (not in avoid list)",
            "art_style": "one from art_style_pool (not in avoid list)",
            "layout": "one of layout_pool (not in avoid list)",
            "caption": "the IG post caption with 8-12 hashtags",
            "slides": [
                {"pill": "", "headline": "", "hl": "highlighted words (substring of headline)",
                 "sub": "", "image_prompt": "distinct subject, fits palette+art_style"}
            ],
        },
    }
    r = client.chat.completions.create(
        model=C.OPENAI_MODEL, response_format={"type": "json_object"}, temperature=0.8,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": json.dumps(user)}])
    plan = json.loads(r.choices[0].message.content)

    if plan.get("skip") or plan.get("confidence", 0) < 60:
        print(f"[s2] skip day (confidence={plan.get('confidence')})"); return None
    assert len(plan["slides"]) == 5, "need exactly 5 slides"
    plan["date"] = datetime.date.today().isoformat()
    print(f'[s2] story: {plan["story"]["title"]}  | {plan["palette"]}/{plan["art_style"][:18]}/{plan["layout"]}')
    return plan

def commit_ledger(plan):
    ledger = _load(LEDGER, []); history = _load(HISTORY, [])
    ledger.append({"date": plan["date"], "palette": plan["palette"],
                   "art_style": plan["art_style"], "layout": plan["layout"],
                   "motifs": [s["image_prompt"][:40] for s in plan["slides"]]})
    history.append({"date": plan["date"], "title": plan["story"]["title"]})
    LEDGER.write_text(json.dumps(ledger[-60:], indent=2))
    HISTORY.write_text(json.dumps(history[-200:], indent=2))

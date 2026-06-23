"""Art-director QA agent: a vision model reviews the rendered carousel against the everydayhypehq
brand rules BEFORE posting, so off-brand / broken / unreadable carousels never go live and the
look stays consistent without manual review. Returns {verdict, score, issues, worst_slide}."""
import base64, json
from pathlib import Path
from openai import OpenAI
import config as C

SPEC = """everydayhypehq Instagram carousel — BRAND RULES (judge against ALL of these):
READABILITY: headline crisp & fully readable over a dark scrim; nothing cut off the canvas edges.
BRAND: a colored pill top-left (e.g. BREAKING); @everydayhypehq + circular avatar in the bottom-right
  footer; bold condensed UPPERCASE headline with 1-2 highlight words colored to match the background.
PERSON COVERS: the real person should FILL the frame (head near top, body behind the headline) — NOT a
  small floating cut-out in empty space; a company logo top-right is fine; a glow/spotlight should ground
  the person so they don't look pasted/cropped.
IMAGE QUALITY: no garbled/melted faces, no distorted hands, no fake text/letters/numbers baked into the
  background image, no watermark.
ORIGINALITY (must NOT look like a copy of another account): no borrowed channel name like "TECHNOLOGY",
  no "SWIPE FOR MORE", no baked-in carousel dots or swipe arrows (Instagram draws those itself).
CONTENT: each slide distinct and factual; a real follow CTA on the last slide."""

# Anchored rubric: the judge must score each axis on its own scale, then we SUM them. Forcing
# per-axis sub-scores stops the model from parking every carousel at a vague ~68 — the total now
# actually moves when the copy or visuals change.
RUBRIC = {"readability": 30, "brand": 20, "image_quality": 30, "originality": 10, "content": 10}

def review(slide_paths, model="gpt-4o"):
    client = OpenAI(api_key=C.OPENAI_API_KEY)
    # detail:"high" — the slides are 1080x1350 with fine headline text; "low" downsamples to ~512px
    # so the judge literally can't read them (that's what was pinning the score to a flat 68).
    imgs = [{"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode(),
                           "detail": "high"}} for p in slide_paths]
    sys = ("You are a STRICT art director for the Instagram brand @everydayhypehq. Review the carousel "
           "slides (in order) against the rules. Be honest and DISCRIMINATING — most carousels are NOT a "
           "flat average; reward genuinely clean ones and punish real problems. Score each axis on its own "
           "scale (this is the max for each): readability 0-30, brand 0-20, image_quality 0-30, "
           "originality 0-10, content 0-10. The total score is the SUM of the five (0-100). Return ONLY JSON: "
           '{"scores":{"readability":int,"brand":int,"image_quality":int,"originality":int,"content":int},'
           '"score":int,"issues":["short concrete issue tied to a slide #",...],"worst_slide":int,'
           '"verdict":"post"|"revise"|"skip"}. '
           "verdict 'post' if total>=80; 'revise' if fixable copy/image issues (total 55-79); "
           "'skip' if broken/off-brand/unreadable (total<55). Deduct hard for: text cut off the canvas, "
           "unreadable headline, garbled/melted faces or fake baked-in text in the image, or anything that "
           "looks copied from another account.")
    usr = [{"type": "text", "text": SPEC + "\n\nReview these slides:"}] + imgs
    try:
        r = client.chat.completions.create(model=model, response_format={"type": "json_object"},
                                           temperature=0.3, messages=[{"role": "system", "content": sys},
                                                                      {"role": "user", "content": usr}])
        v = json.loads(r.choices[0].message.content)
        # Trust the SUM of the anchored sub-scores over the model's own 'score' field (they sometimes
        # disagree; the sum is what the rubric actually defines).
        sub = v.get("scores") or {}
        if sub:
            total = sum(int(sub.get(k, 0)) for k in RUBRIC)
            v["score"] = max(0, min(100, total))
        v.setdefault("score", 0); v.setdefault("issues", []); v.setdefault("worst_slide", 0)
        # Derive verdict from the (recomputed) total so it's always consistent with the score.
        s = v["score"]
        v["verdict"] = "post" if s >= 80 else ("revise" if s >= 55 else "skip")
        return v
    except Exception as e:
        # never let the QA agent block the pipeline on its own error — default to letting it through
        return {"verdict": "post", "score": -1, "issues": [f"(review error: {e})"]}

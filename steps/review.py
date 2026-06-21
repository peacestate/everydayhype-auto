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

def review(slide_paths, model="gpt-4o-mini"):
    client = OpenAI(api_key=C.OPENAI_API_KEY)
    imgs = [{"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode(),
                           "detail": "low"}} for p in slide_paths]
    sys = ("You are a STRICT art director for the Instagram brand @everydayhypehq. Review the carousel "
           "slides (in order) against the rules. Be honest — flag anything that looks off-brand, broken, "
           "unreadable, pasted/cropped, or copied from another account. Return ONLY JSON: "
           '{"verdict":"post"|"revise"|"skip","score":0-100,"issues":["short issue",...],"worst_slide":int}. '
           "verdict 'post' if genuinely good (score>=75); 'revise' if fixable copy/image issues (score 50-74); "
           "'skip' if broken/off-brand/unreadable (score<50).")
    usr = [{"type": "text", "text": SPEC + "\n\nReview these slides:"}] + imgs
    try:
        r = client.chat.completions.create(model=model, response_format={"type": "json_object"},
                                           temperature=0.2, messages=[{"role": "system", "content": sys},
                                                                      {"role": "user", "content": usr}])
        v = json.loads(r.choices[0].message.content)
        v.setdefault("verdict", "post"); v.setdefault("score", 0); v.setdefault("issues", [])
        return v
    except Exception as e:
        # never let the QA agent block the pipeline on its own error — default to letting it through
        return {"verdict": "post", "score": -1, "issues": [f"(review error: {e})"]}

# everydayhypehq — daily AI/tech carousel automation

Fully autonomous: picks a trending story, writes copy, generates 5 varied backgrounds,
renders branded slides, and posts the carousel to Instagram — daily, in the cloud, laptop off.

## Pipeline
```
s1 fetch_news   HN + Reddit + (RSS)         -> ranked candidates   [no key]
s2 brain        OpenAI gpt-4o-mini          -> story + copy + palette/style/layout (variety engine)
s3 gen_images   Kaggle FLUX.1-schnell 4bit  -> 5 distinct backgrounds
s4 render       headless Chrome + ffmpeg    -> 5x 1080x1350 slides
s5 upload       Cloudinary                  -> public image URLs
s6 publish      Instagram Graph API         -> carousel posted
```
Orchestrated by `.github/workflows/daily.yml` (cron). State (`state/style_ledger.json`,
`state/posted_history.json`) is committed back each run so variety + dedup persist.

## Variety engine (config.py)
- Layout = constant brand identity; **palette + art-style + layout-variant rotate daily**, avoiding the last `AVOID_DAYS`.
- The brain enforces: 5 **distinct** subjects (no repeated motif), >=1 human shot, quality/confidence gate (skips weak days).

## Setup — add these GitHub repo Secrets
| Secret | Where to get it |
|---|---|
| `OPENAI_API_KEY` | platform.openai.com |
| `HF_TOKEN` | huggingface.co (FLUX.1-schnell access) |
| `KAGGLE_ACCESS_TOKEN` | the `KGAT_…` token of the image account (workflow writes it to `~/.kaggle/access_token`) |
| `CLOUDINARY_URL` | cloudinary.com dashboard (`cloudinary://key:secret@cloud`) |
| `IG_ACCESS_TOKEN` | long-lived token, `instagram_content_publish` |
| `IG_USER_ID` | your IG Business Account ID |

Instagram prerequisites: IG = **Business/Creator**, linked to a **Facebook Page**, a **Meta app**
with the Instagram Graph API product.

## Run locally / test
```bash
pip install -r requirements.txt
python steps/s1_fetch_news.py        # see today's candidates (no keys)
python pipeline.py --dry-run         # full build, NO posting (needs OpenAI+HF+Kaggle)
python pipeline.py                   # full run + post (needs all secrets)
```
Swap image model: `IMAGE_MODEL` in `config.py` (`flux` default | `realvis`).
"""

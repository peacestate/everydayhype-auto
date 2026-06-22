"""everydayhypehq carousel automation — central config.
Brand layout stays constant (recognizable identity); the VISUAL layer rotates daily
(palette + art-style + layout variant) so the feed never looks copy-pasted.
See [[everydayhype-carousel]] / [[everydayhype-automation]] in memory."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
WORK  = ROOT / "work"          # per-run scratch (bg images, rendered slides)
TEMPLATES = ROOT / "templates"
for d in (STATE, WORK): d.mkdir(exist_ok=True)

BRAND = "@everydayhypehq"
CANVAS_W, CANVAS_H = 1080, 1350           # IG 4:5

# --- secrets (from env / GitHub Secrets) ---
OPENAI_API_KEY      = os.environ.get("OPENAI_API_KEY", "")
HF_TOKEN            = os.environ.get("HF_TOKEN", "")
KAGGLE_ACCESS_TOKEN = os.environ.get("KAGGLE_ACCESS_TOKEN", "")  # KGAT image-acct token (CI writes ~/.kaggle/access_token)
CLOUDINARY_URL      = os.environ.get("CLOUDINARY_URL", "")       # cloudinary://key:secret@cloud
IG_TOKEN            = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER_ID          = os.environ.get("IG_USER_ID", "")           # IG Business Account ID
TG_TOKEN            = os.environ.get("TELEGRAM_BOT_TOKEN", "")    # @BotFather bot token (daily preview DM)
TG_CHAT             = os.environ.get("TELEGRAM_CHAT_ID", "")      # your Telegram chat id
GH_PAT              = os.environ.get("GH_PAT", "")               # optional PAT — lets 🔄 Redo re-dispatch daily.yml
GH_REPO             = os.environ.get("GH_REPO", "kiAnukal/everydayhype-auto")

# minutes a queued post waits for your decision before auto-posting (the "almost 2 hours" rule)
APPROVAL_DEADLINE_MIN = int(os.environ.get("APPROVAL_DEADLINE_MIN", "120"))

# --- model / kaggle ---
OPENAI_MODEL = "gpt-4o-mini"                                  # brain: rank + copy + image-judge
KAGGLE_KERNEL = os.environ.get("KAGGLE_KERNEL", "anuragmishra108/everydayhype-flux")
IMAGE_MODEL  = "flux"            # "flux" (default) | "realvis"  -> swappable

# --- the VARIETY ENGINE pools (brain picks, avoiding recent history) ---
PALETTES = [
    {"name":"red",     "accent":"#ff2740", "accent2":"#19e3ff"},
    {"name":"cyan",    "accent":"#19e3ff", "accent2":"#ff2740"},
    {"name":"purple",  "accent":"#b16cff", "accent2":"#19e3ff"},
    {"name":"amber",   "accent":"#ffb020", "accent2":"#19e3ff"},
    {"name":"green",   "accent":"#28e08a", "accent2":"#ff2740"},
    {"name":"blue",    "accent":"#3d7bff", "accent2":"#ff8a3d"},
    {"name":"magenta", "accent":"#ff3da6", "accent2":"#19e3ff"},
]
ART_STYLES = [
    "photoreal cinematic, volumetric light, 8k",
    "sleek 3D render, octane, glossy materials",
    "neon glow synthwave, bloom, dark background",
    "isometric miniature diorama, tilt-shift",
    "dramatic macro close-up, shallow depth",
    "double-exposure, silhouette blended with data",
]
LAYOUTS = ["a", "b", "c"]        # template html variants
AVOID_DAYS = 6                    # don't reuse a palette/style/layout within this many days

# section pill labels per slide position (emoji rotates a bit; brain may tweak)
PILLS = ["BREAKING 🔴", "WHAT HAPPENED ⚡", "WHY IT MATTERS 🌍", "THE IMPACT 🔐", "THE TAKEAWAY 🔥"]

"""One-off recovery: republish the EXACT carousel the user approved at 4:32 PM IST (control_msg 31).

Why this exists: s5_upload.py used a date-only Cloudinary path (public_id 'slide_{i}'), so the
6:20 PM re-render overwrote the 4:32 PM slides at that same path. Publishing the approved record
then fetched the wrong (6:20) visuals. The original 4:32 slides survive as the daily-carousel
workflow artifact (run 27947084732); recover.yml downloads them into ./recover_slides/ and this
module re-uploads them to a UNIQUE, un-overwritable path and posts them with the approved caption.
"""
import json, os
import cloudinary, cloudinary.uploader
import config as C
from steps import s6_publish

REC = json.load(open("state/recover432.json", encoding="utf-8"))
caption = REC["caption"]

paths = [f"recover_slides/slide_{i}.png" for i in range(1, 6)]
missing = [p for p in paths if not os.path.exists(p)]
assert not missing, f"missing recovered slides: {missing}"

os.environ["CLOUDINARY_URL"] = C.CLOUDINARY_URL
cloudinary.config(secure=True)
urls = []
for i, p in enumerate(paths, 1):
    res = cloudinary.uploader.upload(
        p, folder="everydayhypehq/2026-06-22",
        public_id=f"approved432_slide_{i}", overwrite=True)  # unique name -> safe to overwrite itself
    urls.append(res["secure_url"])
print("[recover] uploaded originals:\n  " + "\n  ".join(urls))

media_id = s6_publish.publish(urls, caption)
print(f"[recover] PUBLISHED corrected 4:32 carousel -> {media_id}")

hist_path = "state/posted_history.json"
hist = json.load(open(hist_path, encoding="utf-8")) if os.path.exists(hist_path) else []
hist.append({"date": "2026-06-22",
             "title": "Apertus — 4:32 approved (corrected original images)",
             "media_id": media_id})
open(hist_path, "w", encoding="utf-8").write(json.dumps(hist, indent=2, ensure_ascii=False))
print("[recover] recorded in posted_history.json")

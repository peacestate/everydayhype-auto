"""Step 5 — upload slides to Cloudinary -> public HTTPS URLs (IG Graph API needs URLs, not bytes).
Configured automatically from the CLOUDINARY_URL env var (cloudinary://key:secret@cloud)."""
import os, datetime
import cloudinary, cloudinary.uploader
import config as C

def upload(slide_paths):
    os.environ["CLOUDINARY_URL"] = C.CLOUDINARY_URL    # cloudinary.config() auto-parses this
    cloudinary.config(secure=True)
    day = datetime.date.today().isoformat()
    # Unique per-render id so re-renders (improve/redo/next daily) NEVER overwrite the slides
    # of an already-queued/approved post. Previously public_id was a fixed "slide_{i}" in a
    # date-only folder, so a later render clobbered an approved post's images at the same path
    # and publishing fetched the wrong (latest) visuals.
    run_id = datetime.datetime.utcnow().strftime("%H%M%S")
    urls = []
    for i, p in enumerate(slide_paths, 1):
        res = cloudinary.uploader.upload(str(p), folder=f"everydayhypehq/{day}",
                                         public_id=f"{run_id}_slide_{i}", overwrite=False)
        urls.append(res["secure_url"])
    print(f"[s5] uploaded {len(urls)} slides to Cloudinary (run {run_id})")
    return urls

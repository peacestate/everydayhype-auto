"""Step 5 — upload slides to Cloudinary -> public HTTPS URLs (IG Graph API needs URLs, not bytes).
Configured automatically from the CLOUDINARY_URL env var (cloudinary://key:secret@cloud)."""
import os, datetime
import cloudinary, cloudinary.uploader
import config as C

def upload(slide_paths):
    os.environ["CLOUDINARY_URL"] = C.CLOUDINARY_URL    # cloudinary.config() auto-parses this
    cloudinary.config(secure=True)
    day = datetime.date.today().isoformat()
    urls = []
    for i, p in enumerate(slide_paths, 1):
        res = cloudinary.uploader.upload(str(p), folder=f"everydayhypehq/{day}",
                                         public_id=f"slide_{i}", overwrite=True)
        urls.append(res["secure_url"])
    print(f"[s5] uploaded {len(urls)} slides to Cloudinary")
    return urls

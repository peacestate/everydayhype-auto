"""Step 6 — publish the carousel via the Instagram Graph API.
Flow: per-image child container (is_carousel_item) -> CAROUSEL container (children+caption) -> publish."""
import re, time, requests
import config as C

GRAPH = "https://graph.facebook.com/v21.0"

# IG's media fetcher officially accepts JPEG ONLY. PNG works by accident and fails
# unpredictably per-image with error 9004 / subcode 2207052 ("Media download has failed").
# 2026-09-03: slide 3 of a perfectly valid 1080x1350 PNG set was refused twice, 3h apart,
# while slides 1-2 of the same set were accepted. So never hand IG a .png — rewrite
# Cloudinary delivery URLs to an on-the-fly JPEG transcode (no re-upload needed, which
# also repairs posts already queued in state/pending.json with .png URLs).
_CLD = re.compile(r"^(https://res\.cloudinary\.com/[^/]+/image/upload/)(.*)\.png$", re.I)

def as_jpeg(url):
    m = _CLD.match(url.strip())
    if not m:
        return url
    head, rest = m.group(1), m.group(2)
    if rest.startswith("f_jpg"):     # already normalised
        return f"{head}{rest}.jpg"
    return f"{head}f_jpg,q_90/{rest}.jpg"

def _post(path, **params):
    params["access_token"] = C.IG_TOKEN
    r = requests.post(f"{GRAPH}/{path}", data=params, timeout=60)
    j = r.json()
    if "error" in j: raise RuntimeError(f"IG API error: {j['error']}")
    return j

def _wait_ready(container_id, tries=20):
    for _ in range(tries):
        r = requests.get(f"{GRAPH}/{container_id}",
                         params={"fields": "status_code", "access_token": C.IG_TOKEN}, timeout=30).json()
        if r.get("status_code") == "FINISHED": return
        if r.get("status_code") == "ERROR": raise RuntimeError("container processing ERROR")
        time.sleep(5)
    raise TimeoutError("container not ready")

def _child(url, tries=3):
    """Create one carousel child container, retrying IG's flaky media fetch.

    A single refused image used to abort the whole carousel and lose the day's post,
    so give each URL a few attempts with backoff before giving up."""
    last = None
    for attempt in range(1, tries + 1):
        try:
            return _post(f"{C.IG_USER_ID}/media", image_url=url, is_carousel_item="true")["id"]
        except Exception as e:
            last = e
            print(f"[s6] child attempt {attempt}/{tries} failed for {url}: {e}")
            if attempt < tries:
                time.sleep(5 * attempt)
    raise RuntimeError(f"could not create child container for {url}: {last}")

def publish(image_urls, caption):
    # 1) child containers (JPEG only — see as_jpeg)
    urls = [as_jpeg(u) for u in image_urls]
    children = [_child(u) for u in urls]
    for cid in children: _wait_ready(cid)
    # 2) carousel container
    carousel = _post(f"{C.IG_USER_ID}/media", media_type="CAROUSEL",
                     children=",".join(children), caption=caption)["id"]
    _wait_ready(carousel)
    # 3) publish
    pub = _post(f"{C.IG_USER_ID}/media_publish", creation_id=carousel)
    print(f"[s6] PUBLISHED carousel, media id = {pub.get('id')}")
    return pub.get("id")

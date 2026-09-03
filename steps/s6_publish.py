"""Step 6 — publish the carousel via the Instagram Graph API.
Flow: per-image child container (is_carousel_item) -> CAROUSEL container (children+caption) -> publish."""
import datetime, os, time, requests
import config as C

GRAPH = "https://graph.facebook.com/v21.0"

def _bust(url, n):
    """Last-resort fallback: append a throwaway query param. Weaker than _fresh_copy —
    changing the URL string alone was NOT enough to clear a 9004 (see _child)."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}_r={n}"

def _fresh_copy(url, n):
    """Copy the image to a NEW Cloudinary public_id and return that URL.

    This is the only thing empirically proven to clear a 9004 (see _child). Cloudinary
    fetches the source URL server-side, so this works at publish time even though the
    rendered slides are long gone from disk. Falls back to _bust if Cloudinary isn't
    configured or the copy fails, so a retry is still attempted either way."""
    if not C.CLOUDINARY_URL:
        print("[s6] no CLOUDINARY_URL at publish time — falling back to a cache-busted URL")
        return _bust(url, n)
    try:
        os.environ["CLOUDINARY_URL"] = C.CLOUDINARY_URL   # config() parses the env var, not a kwarg
        import cloudinary, cloudinary.uploader
        cloudinary.config(secure=True)
        stamp = datetime.datetime.utcnow().strftime("%H%M%S")
        res = cloudinary.uploader.upload(
            url, folder=f"everydayhypehq/{datetime.date.today().isoformat()}",
            public_id=f"retry{stamp}_{n}", overwrite=True)
        print(f"[s6] re-uploaded under a fresh public_id -> {res['secure_url']}")
        return res["secure_url"]
    except Exception as e:
        print(f"[s6] fresh copy failed ({e}) — falling back to a cache-busted URL")
        return _bust(url, n)

def _post(path, **params):
    params["access_token"] = C.IG_TOKEN
    r = requests.post(f"{GRAPH}/{path}", data=params, timeout=60)
    try:
        j = r.json()
    except ValueError:   # a gateway/HTML error page, not JSON — say so instead of dying opaquely
        raise RuntimeError(f"IG API returned HTTP {r.status_code}, non-JSON body: {r.text[:300]!r}")
    if "error" in j: raise RuntimeError(f"IG API error: {j['error']}")
    return j

def _wait_ready(container_id, tries=20):
    # Ask for `status` too: status_code is just "ERROR", while status carries the actual reason.
    # A bare "container processing ERROR" tells you nothing at 4am.
    last = {}
    for _ in range(tries):
        last = requests.get(f"{GRAPH}/{container_id}",
                            params={"fields": "status_code,status", "access_token": C.IG_TOKEN},
                            timeout=30).json()
        if last.get("status_code") == "FINISHED": return
        if last.get("status_code") == "ERROR":
            raise RuntimeError(f"container {container_id} processing ERROR: {last.get('status') or last}")
        time.sleep(5)
    raise TimeoutError(f"container {container_id} not ready after {tries} polls "
                       f"(last status_code={last.get('status_code')!r})")

def _child(url, tries=4):
    """Create one carousel child container, working around IG's poisoned URL cache.

    2026-09-03: slide 3 of a valid 1080x1350 set was refused with error 9004 / subcode
    2207052 ("Media download has failed") on three separate runs over 3+ hours, while
    slides 1-2 of the same upload went through. The image was fine — Cloudinary served it
    complete, with no access control or moderation, and the same pixels re-uploaded under a
    NEW public_id published immediately.

    Note a URL-STRING change is not enough: an f_jpg transcode of the same image is a
    different URL and was refused instantly, so IG's cache keys on something closer to the
    resolved asset than the raw string. Retrying therefore re-uploads to a fresh public_id.

    One refused image used to abort the whole carousel and lose the day's post."""
    last = None
    for attempt in range(1, tries + 1):
        target = url if attempt == 1 else _fresh_copy(url, attempt)
        try:
            return _post(f"{C.IG_USER_ID}/media", image_url=target, is_carousel_item="true")["id"]
        except Exception as e:
            last = e
            print(f"[s6] child attempt {attempt}/{tries} failed for {target}: {e}")
            if attempt < tries:
                time.sleep(5 * attempt)
    raise RuntimeError(f"could not create child container for {url}: {last}")

def publish(image_urls, caption):
    # 1) child containers
    children = [_child(u) for u in image_urls]
    for cid in children: _wait_ready(cid)
    # 2) carousel container
    carousel = _post(f"{C.IG_USER_ID}/media", media_type="CAROUSEL",
                     children=",".join(children), caption=caption)["id"]
    _wait_ready(carousel)
    # 3) publish
    pub = _post(f"{C.IG_USER_ID}/media_publish", creation_id=carousel)
    print(f"[s6] PUBLISHED carousel, media id = {pub.get('id')}")
    return pub.get("id")

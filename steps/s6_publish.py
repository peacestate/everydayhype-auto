"""Step 6 — publish the carousel via the Instagram Graph API.
Flow: per-image child container (is_carousel_item) -> CAROUSEL container (children+caption) -> publish."""
import time, requests
import config as C

GRAPH = "https://graph.facebook.com/v21.0"

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

def publish(image_urls, caption):
    # 1) child containers
    children = []
    for url in image_urls:
        cid = _post(f"{C.IG_USER_ID}/media", image_url=url, is_carousel_item="true")["id"]
        children.append(cid)
    for cid in children: _wait_ready(cid)
    # 2) carousel container
    carousel = _post(f"{C.IG_USER_ID}/media", media_type="CAROUSEL",
                     children=",".join(children), caption=caption)["id"]
    _wait_ready(carousel)
    # 3) publish
    pub = _post(f"{C.IG_USER_ID}/media_publish", creation_id=carousel)
    print(f"[s6] PUBLISHED carousel, media id = {pub.get('id')}")
    return pub.get("id")

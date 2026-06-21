"""Hero-asset sourcing for person-centric carousel covers.
License-free only: Wikimedia photo (CC/Public Domain) -> rembg cut-out, + company logo via
Wikidata P154 -> Commons. Everything is graceful: any failure returns None and the caller
falls back to a normal FLUX cover. No copyrighted press photos, no AI-generated faces."""
import urllib.request, urllib.parse, json, re
from pathlib import Path

UA = {"User-Agent": "everydayhypehq/1.0 (anuragmishra192000@gmail.com)"}

def _get(u, timeout=25):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout).read()
def _jget(u):
    return json.loads(_get(u))

def person_photo(name):
    """(bytes, credit, license) for a license-free Wikimedia photo of `name`, else None."""
    try:
        s = _jget("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(name.replace(" ", "_")))
        img = (s.get("originalimage") or s.get("thumbnail") or {}).get("source")
        if not img:
            return None
        fn = urllib.parse.unquote(img.split("/")[-1])
        api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
               "&iiprop=extmetadata&titles=" + urllib.parse.quote("File:" + fn))
        md = list(_jget(api)["query"]["pages"].values())[0].get("imageinfo", [{}])[0].get("extmetadata", {})
        lic = md.get("LicenseShortName", {}).get("value", "")
        art = re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", "")).strip()
        art = re.sub(r"(?i)^photographe?r:?\s*", "", art).strip()   # drop "Photographer:" prefix
        if len(art) > 60: art = art[:60].rsplit(" ", 1)[0] + "…"     # never cut mid-word
        if lic and ("cc" in lic.lower() or "public" in lic.lower()):   # free licenses only
            return _get(img), art, lic
        return None
    except Exception:
        return None

def company_logo(company):
    """Logo PNG bytes for `company` via Wikidata P154 -> Commons (mostly PD), else None."""
    try:
        s = _jget("https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&type=item&search=" + urllib.parse.quote(company))
        if not s.get("search"):
            return None
        qid = s["search"][0]["id"]
        c = _jget("https://www.wikidata.org/w/api.php?action=wbgetclaims&format=json&property=P154&entity=" + qid)
        claims = c.get("claims", {}).get("P154")
        if not claims:
            return None
        fn = claims[0]["mainsnak"]["datavalue"]["value"]
        api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
               "&iiprop=url&iiurlwidth=300&titles=" + urllib.parse.quote("File:" + fn))
        ii = list(_jget(api)["query"]["pages"].values())[0]["imageinfo"][0]
        return _get(ii.get("thumburl") or ii.get("url"))
    except Exception:
        return None

def build_hero(person, company, outdir):
    """Fetch photo -> cut-out + logo. Returns {cut, raw, logo, credit, license} or None."""
    if not person:
        return None
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    pp = person_photo(person)
    if not pp:
        return None
    raw, credit, lic = pp
    (outdir / "hero_raw.jpg").write_bytes(raw)
    try:
        from rembg import remove, new_session
        from PIL import Image, ImageFilter
        # isnet-general-use = cleaner edges than the default u2net (less jagged around hands/arms)
        sess = new_session("isnet-general-use")
        cut = remove(Image.open(outdir / "hero_raw.jpg").convert("RGBA"), session=sess)
        r, g, b, a = cut.split()
        a = a.filter(ImageFilter.GaussianBlur(1.3))   # feather the alpha so it isn't hard-cropped
        Image.merge("RGBA", (r, g, b, a)).save(outdir / "hero_cut.png")
    except Exception:
        return None
    logo = company_logo(company) if company else None
    if logo:
        (outdir / "hero_logo.png").write_bytes(logo)
    return {"cut": str(outdir / "hero_cut.png"), "raw": str(outdir / "hero_raw.jpg"),
            "logo": str(outdir / "hero_logo.png") if logo else "",
            "credit": (credit + " · " + lic).strip(" ·"), "license": lic}

if __name__ == "__main__":   # quick self-test
    import sys
    h = build_hero(sys.argv[1] if len(sys.argv) > 1 else "Dario Amodei",
                   sys.argv[2] if len(sys.argv) > 2 else "Anthropic", "work/_herotest")
    print(h)

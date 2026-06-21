"""Step 4 — render the 5 slides. Builds self-contained HTML (bg inlined as base64) from the
plan + palette + layout variant, screenshots via headless Chrome, crops to 1080x1350 PNGs."""
import base64, subprocess, os, shutil, html, colorsys
from pathlib import Path
from PIL import Image
import config as C

SLIDES = C.WORK / "slides"
GAP, PAD = 40, 40

def _bg_accent(path):
    """Highlight color = dominant vivid hue of THIS slide's background (red bg -> red text,
    blue bg -> sky-blue text) so overlay text stays cohesive with whatever news image FLUX makes.
    Falls back to cyan for flat/gray backgrounds."""
    try:
        im = Image.open(path).convert("RGB").resize((120, 150))
        bins = {}
        for r, g, b in im.getdata():
            h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            if s > 0.35 and v > 0.35:
                hb = round(h*24); bins[hb] = bins.get(hb, 0) + 1
        if not bins: return "#19e3ff"
        h = max(bins, key=bins.get)/24.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.80, 1.0)
        return "#%02x%02x%02x" % (int(r*255), int(g*255), int(b*255))
    except Exception:
        return "#19e3ff"

def _chrome():
    for c in [os.environ.get("CHROME_BIN"),
              str(Path.home()/".cache/hyperframes/chrome/chrome-headless-shell/win64-131.0.6778.85/chrome-headless-shell-win64/chrome-headless-shell.exe"),
              "/usr/bin/google-chrome", "/usr/bin/chromium-browser", "chrome-headless-shell"]:
        if c and (shutil.which(c) or Path(c).exists()): return c
    raise RuntimeError("no chrome found; set CHROME_BIN")

def _b64(p): return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()

# layout variants -> where the headline block sits
LAYOUT_CSS = {
    "a": ".content{left:54px;right:54px;bottom:150px}",
    "b": ".content{left:54px;right:54px;top:50%;transform:translateY(-50%);text-align:center}",
    "c": ".content{left:54px;right:380px;bottom:150px}",
}

def _hls(s):
    """Highlight phrases for a slide: supports a list ('hls') or a single ('hl')."""
    raw = s.get("hls") or ([s.get("hl")] if s.get("hl") else [])
    return [str(h).upper().strip() for h in raw if h]

def _mark(headline_upper, hls):
    for p in hls:
        p = html.escape(p)
        if p and p in headline_upper:
            headline_upper = headline_upper.replace(p, f'<span class="hl">{p}</span>', 1)
    return headline_upper

def _dots(i, n):
    return '<div class="dots">' + "".join(f'<i class="{"on" if j==i else ""}"></i>' for j in range(n)) + '</div>'

def _clean(t):
    return "".join(c for c in str(t) if c >= " " or c == "\n").strip()

def _slide_html(i, s, bg_path, n=5):
    headline = _mark(html.escape(s["headline"]).upper(), _hls(s))
    pill_alert = "alert" if i in (0, n-1) else ""
    pill = C.PILLS[i] if i < len(C.PILLS) else s.get("pill", "")
    acc = _bg_accent(bg_path)   # highlight color matches THIS slide's background
    # No baked swipe-arrow / dots: Instagram draws its own native swipe + position indicator.
    return f'''<section class="slide" style="--accent:{acc}">
      <img class="bg" src="{_b64(bg_path)}"><div class="scrim"></div>
      <div class="pill {pill_alert}">{html.escape(pill)}</div>
      <div class="content"><h1>{headline}</h1><p class="sub">{html.escape(s["sub"])}</p></div>
      <div class="brand"><span class="ava"></span><span class="handle">{C.BRAND}</span></div>
      </section>'''

def _hero_cover_html(s, hero, n=5, bg_path=None):
    """Cut-out-CEO cover: license-free photo (bg removed) over the story's FLUX scene (darkened)
    + company logo + bg-matched multi-highlight headline."""
    acc = _bg_accent(bg_path) if bg_path and Path(bg_path).exists() else _bg_accent(hero["raw"])
    headline = _mark(html.escape(s["headline"]).upper(), _hls(s))
    logo = f'<img class="hlogo" src="{_b64(hero["logo"])}">' if hero.get("logo") else ""
    cred = f'<div class="hcred">📷 {html.escape(_clean(hero.get("credit","")))}</div>' if hero.get("credit") else ""
    pill = C.PILLS[0]   # our own "BREAKING 🔴" pill (day1/day2 brand), not a borrowed tag/wording
    backdrop = (f'<img class="hbg" src="{_b64(bg_path)}"><div class="hbgvig"></div>'
                if bg_path and Path(bg_path).exists() else '<div class="hgrid"></div>')
    return f'''<section class="slide hslide" style="--accent:{acc}">
      {backdrop}<div class="hglow"></div><div class="hspot"></div>
      <img class="hhero" src="{_b64(hero["cut"])}">
      <div class="hscrim"></div>{logo}
      <div class="pill alert">{html.escape(pill)}</div>
      <div class="hhead"><h1>{headline}</h1><p class="sub">{html.escape(s["sub"])}</p></div>
      <div class="brand"><span class="ava"></span><span class="handle">{C.BRAND}</span></div>
      {cred}</section>'''

def build_html(plan, bg_dir, hero=None):
    pal = next(p for p in C.PALETTES if p["name"] == plan["palette"])
    layout = LAYOUT_CSS.get(plan["layout"], LAYOUT_CSS["a"])
    parts = []
    for i, s in enumerate(plan["slides"]):
        if i == 0 and hero:
            parts.append(_hero_cover_html(s, hero, len(plan["slides"]), Path(bg_dir)/"1.png"))
        else:
            parts.append(_slide_html(i, s, Path(bg_dir)/f"{i+1}.png", len(plan["slides"])))
    slides = "\n".join(parts)
    css = f"""
    :root{{--accent:#19e3ff}}
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{background:#05060a;display:flex;flex-direction:column;gap:{GAP}px;padding:{PAD}px;align-items:center}}
    .slide{{position:relative;width:{C.CANVAS_W}px;height:{C.CANVAS_H}px;overflow:hidden;background:#05060a;
      font-family:'Archivo','Montserrat',Arial,sans-serif;color:#fff;border-radius:0}}
    .bg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1}}
    .scrim{{position:absolute;inset:0;z-index:2;background:linear-gradient(180deg,rgba(2,4,8,.72)0%,rgba(2,4,8,0)24%),linear-gradient(0deg,rgba(2,4,8,.97)0%,rgba(2,4,8,.88)20%,rgba(2,4,8,0)52%)}}
    .pill{{position:absolute;top:46px;left:46px;z-index:3;display:inline-flex;align-items:center;gap:10px;padding:13px 26px;border-radius:999px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.24);font-weight:800;font-size:26px;letter-spacing:.05em;text-transform:uppercase}}
    .pill.alert{{background:rgba(255,39,64,.20);border-color:rgba(255,39,64,.55)}}
    .content{{position:absolute;z-index:3}}
    {layout}
    h1{{font-family:'Anton','Archivo',sans-serif;font-weight:400;font-size:74px;line-height:1.02;letter-spacing:.005em;text-transform:uppercase;text-shadow:0 4px 30px rgba(0,0,0,.7)}}
    h1 .hl{{color:var(--accent)}}
    .sub{{margin-top:24px;font-weight:600;font-size:31px;color:#dbe4f0;text-shadow:0 2px 16px rgba(0,0,0,.8)}}
    .dots{{position:absolute;left:50%;transform:translateX(-50%);bottom:108px;z-index:3;display:flex;gap:11px}}
    .dots i{{width:9px;height:9px;border-radius:50%;background:rgba(255,255,255,.35)}}
    .dots i.on{{background:#fff;width:26px;border-radius:6px}}
    .brand{{position:absolute;right:46px;bottom:50px;z-index:3;display:flex;align-items:center;gap:14px}}
    .brand .ava{{width:50px;height:50px;border-radius:50%;background:conic-gradient(from 220deg,var(--accent),#b16cff,var(--accent));box-shadow:0 0 0 2px rgba(255,255,255,.25)}}
    .brand .handle{{font-weight:800;font-size:30px;text-shadow:0 2px 14px rgba(0,0,0,.85)}}
    .arrow{{position:absolute;right:40px;top:50%;transform:translateY(-50%);z-index:3;width:60px;height:60px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.32);font-size:40px;color:#fff}}
    /* ---- hero cut-out cover ---- */
    .hslide{{background:#06070d}}
    .hbg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1;filter:brightness(.5) saturate(1.15) blur(2px)}}
    .hbgvig{{position:absolute;inset:0;z-index:1;background:radial-gradient(125% 100% at 68% 32%,transparent 0%,rgba(4,5,11,.5) 70%,rgba(4,5,11,.82) 100%)}}
    .hglow{{position:absolute;right:-8%;top:6%;width:80%;height:60%;z-index:1;background:radial-gradient(circle at 60% 42%,var(--accent) 0%,transparent 60%);opacity:.28;filter:blur(26px);mix-blend-mode:screen}}
    .hgrid{{position:absolute;inset:0;z-index:1;opacity:.08;background-image:linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px);background-size:64px 64px}}
    .hhero{{position:absolute;right:-4%;bottom:120px;height:90%;z-index:2;filter:drop-shadow(0 14px 34px rgba(0,0,0,.85)) drop-shadow(0 0 26px var(--accent))}}
    .hspot{{position:absolute;right:-4%;bottom:120px;width:86%;height:88%;z-index:1;background:radial-gradient(ellipse 56% 58% at 60% 42%,rgba(0,0,0,.5) 0%,transparent 70%)}}
    .hscrim{{position:absolute;inset:0;z-index:3;background:linear-gradient(0deg,rgba(4,5,11,.98)0%,rgba(4,5,11,.9)24%,rgba(4,5,11,0)52%),linear-gradient(180deg,rgba(4,5,11,.65)0%,transparent 16%)}}
    .hlogo{{position:absolute;top:54px;right:54px;z-index:4;width:120px;height:120px;object-fit:contain;border-radius:24px;background:#fff;padding:16px;border:1px solid rgba(255,255,255,.25)}}
    .hhead{{position:absolute;left:54px;right:54px;bottom:190px;z-index:4}}
    .hhead h1{{font-size:80px;line-height:1.0}}
    .hcred{{position:absolute;left:48px;bottom:24px;z-index:4;font-size:16px;color:rgba(255,255,255,.5)}}
    """
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@800;900&family=Montserrat:wght@600;700;800;900&display=swap" rel="stylesheet">
    <style>{css}</style></head><body>{slides}</body></html>"""
    out = C.WORK / "carousel.html"; out.write_text(doc, encoding="utf-8")
    return out

def render(plan, bg_dir, hero=None):
    shutil.rmtree(SLIDES, ignore_errors=True); SLIDES.mkdir(parents=True, exist_ok=True)
    page = build_html(plan, bg_dir, hero)
    full = C.WORK / "_full.png"
    n = len(plan["slides"])
    win_h = PAD*2 + n*C.CANVAS_H + (n-1)*GAP
    subprocess.run([_chrome(), "--headless", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", f"--window-size={C.CANVAS_W+2*PAD},{win_h}",
                    "--virtual-time-budget=8000", f"--screenshot={full}", page.as_uri()],
                   capture_output=True)
    for i in range(n):
        y = PAD + i*(C.CANVAS_H+GAP)
        subprocess.run(["ffmpeg", "-i", str(full), "-vf",
                        f"crop={C.CANVAS_W}:{C.CANVAS_H}:{PAD}:{y}",
                        str(SLIDES/f"slide_{i+1}.png"), "-y"], capture_output=True)
    out = sorted(SLIDES.glob("slide_*.png"))
    print(f"[s4] rendered {len(out)} slides")
    return out

"""Step 4 — render the 5 slides. Builds self-contained HTML (bg inlined as base64) from the
plan + palette + layout variant, screenshots via headless Chrome, crops to 1080x1350 PNGs."""
import base64, subprocess, os, shutil, html
from pathlib import Path
import config as C

SLIDES = C.WORK / "slides"
GAP, PAD = 40, 40

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

def _slide_html(i, s, accent, bg_b64, n=5):
    headline = html.escape(s["headline"]).upper()
    hl = html.escape(s.get("hl", "")).upper()
    if hl and hl in headline:
        headline = headline.replace(hl, f'<span class="hl">{hl}</span>', 1)
    pill_alert = "alert" if i in (0, n-1) else ""
    arrow = '<div class="arrow">›</div>' if i == 0 else ""
    # No baked-in dots: Instagram draws its own native carousel indicator, so
    # an in-image dot row just duplicates it. Let IG handle slide position.
    return f'''<section class="slide">
      <img class="bg" src="{bg_b64}"><div class="scrim"></div>
      <div class="pill {pill_alert}">{html.escape(s["pill"])}</div>
      <div class="content"><h1>{headline}</h1><p class="sub">{html.escape(s["sub"])}</p></div>
      <div class="logo"></div><div class="handle">{C.BRAND}</div>
      {arrow}</section>'''

def build_html(plan, bg_dir):
    pal = next(p for p in C.PALETTES if p["name"] == plan["palette"])
    layout = LAYOUT_CSS.get(plan["layout"], LAYOUT_CSS["a"])
    slides = "\n".join(_slide_html(i, s, pal["accent"], _b64(Path(bg_dir)/f"{i+1}.png"))
                       for i, s in enumerate(plan["slides"]))
    css = f"""
    :root{{--accent:{pal['accent']};--accent2:{pal['accent2']}}}
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{background:#05060a;display:flex;flex-direction:column;gap:{GAP}px;padding:{PAD}px;align-items:center}}
    .slide{{position:relative;width:{C.CANVAS_W}px;height:{C.CANVAS_H}px;overflow:hidden;background:#05060a;
      font-family:'Archivo','Montserrat',Arial,sans-serif;color:#fff;border-radius:0}}
    .bg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1}}
    .scrim{{position:absolute;inset:0;z-index:2;background:linear-gradient(180deg,rgba(2,4,8,.78)0%,rgba(2,4,8,0)26%),linear-gradient(0deg,rgba(2,4,8,.96)0%,rgba(2,4,8,.85)24%,rgba(2,4,8,0)56%)}}
    .pill{{position:absolute;top:46px;left:46px;z-index:3;display:inline-flex;align-items:center;gap:10px;padding:14px 26px;border-radius:999px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.22);font-weight:800;font-size:26px;letter-spacing:.06em;text-transform:uppercase}}
    .pill.alert{{background:rgba(255,39,64,.18);border-color:rgba(255,39,64,.5)}}
    .content{{position:absolute;z-index:3}}
    {layout}
    h1{{font-weight:900;font-size:76px;line-height:1.02;text-transform:uppercase;text-shadow:0 4px 30px rgba(0,0,0,.65)}}
    h1 .hl{{color:var(--accent)}}
    .sub{{margin-top:22px;font-weight:600;font-size:30px;color:#c9d2e0;text-shadow:0 2px 16px rgba(0,0,0,.7)}}
    .logo{{position:absolute;left:46px;bottom:46px;z-index:3;width:54px;height:54px;border-radius:50%;background:conic-gradient(from 220deg,var(--accent),var(--accent2),var(--accent))}}
    .handle{{position:absolute;right:46px;bottom:56px;z-index:3;font-weight:800;font-size:30px;text-shadow:0 2px 14px rgba(0,0,0,.8)}}
    .dots{{position:absolute;left:50%;transform:translateX(-50%);bottom:64px;z-index:3;display:flex;gap:11px}}
    .dots i{{width:9px;height:9px;border-radius:50%;background:rgba(255,255,255,.35)}}
    .dots i.on{{background:#fff;width:24px;border-radius:6px}}
    .arrow{{position:absolute;right:40px;top:50%;transform:translateY(-50%);z-index:3;width:60px;height:60px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.3);font-size:40px;color:#fff}}
    """
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@800;900&family=Montserrat:wght@600;700;800;900&display=swap" rel="stylesheet">
    <style>{css}</style></head><body>{slides}</body></html>"""
    out = C.WORK / "carousel.html"; out.write_text(doc, encoding="utf-8")
    return out

def render(plan, bg_dir):
    shutil.rmtree(SLIDES, ignore_errors=True); SLIDES.mkdir(parents=True, exist_ok=True)
    page = build_html(plan, bg_dir)
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

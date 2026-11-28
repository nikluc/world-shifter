"""CrazyGames cover images, rendered by the real game (no mock-ups).

Opens index.html in Edge, loads a level, lets the ball fall for a moment (so it has a trail and
speed lines), freezes the game loop, tilts the world, hides every button, and lays the game's own
"WORLD / SHIFTER" title over it. CrazyGames rules: title text only, no borders, no icons, not blurry.

    python world-shifter/tools/make_covers.py --sheet          # contact sheet of candidate levels
    python world-shifter/tools/make_covers.py                  # the 3 covers -> builds/crazygames-assets/
"""
import argparse, json, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
GAME = (ROOT / "world-shifter" / "index.html").as_uri()
OUT = ROOT / "builds" / "crazygames-assets"
SEEN = json.dumps({k: 1 for k in ["moving", "bounce", "glue", "ice", "portal", "gem", "water", "moon", "underwater"]})

# ---- the chosen shot (tune here) ----
COVER = {"level": 180, "fall_ms": 1500, "tilt": 0.45, "zoom": 1.45}  # underwater world: portal, spikes, gem, bubbles
SIZES = {"landscape": (1920, 1080), "portrait": (800, 1200), "square": (800, 800)}

INIT = ("localStorage.clear();localStorage.setItem('ws_seen'," + json.dumps(SEEN) + ");"
        "localStorage.setItem('ws_econ',JSON.stringify({wallet:0,gift:{last:new Date().toLocaleDateString('sv'),step:1}}));"
        "localStorage.setItem('ws_muted','1');window.__botQuiet=true;")

# freeze: stop the loop, tilt, shift the world sideways (dx, dy in screen px), draw one frame
FREEZE = """([tilt, dx, dy, zoom]) => {
  window.requestAnimationFrame = () => 0;
  shake = 0; level.view /= zoom; cam.x = ball.x; cam.y = ball.y;
  const scale = Math.min(W, H) / level.view;
  cam.x -= (dx * Math.cos(tilt) + dy * Math.sin(tilt)) / scale;
  cam.y -= (-dx * Math.sin(tilt) + dy * Math.cos(tilt)) / scale;
  for (const el of document.body.children) if (el.tagName !== 'CANVAS' && el.tagName !== 'SCRIPT') el.style.visibility = 'hidden';
  // covers only: skip the little gravity marker (the ▼ at the bottom), the game itself is unchanged
  const mt = ctx.moveTo, fl = ctx.fill; let skip = false;
  ctx.moveTo = function (x, y) { skip = x === W / 2 - 9 && y === H - 46; return mt.call(this, x, y); };
  ctx.fill = function (...a) { if (skip) { skip = false; return; } return fl.apply(this, a); };
  render(performance.now());
}"""

TITLE_CSS = """
#cvTitle{position:fixed;z-index:99;display:flex;flex-direction:column;align-items:center;font-family:'Baloo 2',system-ui;font-weight:800;
  line-height:.84;letter-spacing:.04em;pointer-events:none}
#cvTitle span{color:#fff;-webkit-text-stroke:var(--k) #1a0f3d;paint-order:stroke fill;text-shadow:0 var(--d) 0 #6b3fd6,0 calc(var(--d)*2) 24px rgba(0,0,0,.55)}
#cvTitle .l2{color:#ffd34d;text-shadow:0 var(--d) 0 #c0702a,0 calc(var(--d)*2) 24px rgba(0,0,0,.55);transform:rotate(-5deg)}
"""


def shot(pg, size, level, fall_ms, tilt, dx=0, dy=0, title=None, path=None, zoom=1.0):
    pg.set_viewport_size({"width": size[0], "height": size[1]})
    pg.goto(GAME); pg.wait_for_timeout(500)
    pg.evaluate(f"loadLevel({level}); hide('card'); hide('gift'); hide('menu'); waiting=false; freeze=0; state='play'; angle=targetAngle={tilt}; angVel=0;")
    pg.wait_for_timeout(fall_ms)  # the ball rolls off and falls in the tilted world
    pg.evaluate(f"angle=targetAngle={tilt}")
    pg.evaluate(FREEZE, [tilt, dx, dy, zoom])
    if title:
        pg.add_style_tag(content=TITLE_CSS)
        pg.evaluate("""([css, html]) => { const d = document.createElement('div'); d.id = 'cvTitle'; d.style.cssText = css; d.innerHTML = html; document.body.appendChild(d); }""",
                    [title, "<span>WORLD</span><span class='l2'>SHIFTER</span>"])
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(150)
    pg.screenshot(path=str(path))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sheet", action="store_true"); ap.add_argument("--levels", default=""); ap.add_argument("--level", type=int); ap.add_argument("--tilt", type=float); ap.add_argument("--fall", type=int); ap.add_argument("--zoom", type=float); ap.add_argument("--tag", default="")
    a = ap.parse_args()
    for k, v in (("level", a.level), ("tilt", a.tilt), ("fall_ms", a.fall), ("zoom", a.zoom)):
        if v is not None: COVER[k] = v
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(); pg.add_init_script(INIT)
        if a.sheet:
            levels = [int(x) for x in a.levels.split(",")] if a.levels else [3, 8, 14, 22, 30, 41, 55, 63, 77, 90, 104, 120, 150, 180, 220, 260]
            for lv in levels:
                shot(pg, (480, 480), lv, COVER["fall_ms"], COVER["tilt"], zoom=COVER["zoom"], path=OUT / f"sheet-{lv:03d}.png")
            print("sheet:", OUT)
        else:
            L, F, T, Z = COVER["level"], COVER["fall_ms"], COVER["tilt"], COVER["zoom"]
            # landscape: world on the right, title on the left
            shot(pg, SIZES["landscape"], L, F, T, dx=330, dy=0, path=OUT / f"cover-landscape-1920x1080{a.tag}.png", zoom=Z * 1.3,
                 title="left:6%;top:50%;transform:translateY(-50%);font-size:170px;--k:14px;--d:10px")
            # portrait: title on top, world below
            shot(pg, SIZES["portrait"], L, F, T, dx=0, dy=150, path=OUT / f"cover-portrait-800x1200{a.tag}.png", zoom=Z,
                 title="left:50%;top:5%;transform:translateX(-50%);font-size:128px;--k:11px;--d:8px")
            # square: title on top, world below, a little smaller
            shot(pg, SIZES["square"], L, F, T, dx=0, dy=120, path=OUT / f"cover-square-800x800{a.tag}.png", zoom=Z,
                 title="left:50%;top:4%;transform:translateX(-50%);font-size:104px;--k:9px;--d:7px")
            print("covers:", OUT)
        b.close()


if __name__ == "__main__":
    main()

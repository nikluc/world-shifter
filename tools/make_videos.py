"""CrazyGames preview videos, recorded from the real game.

For each clip level, a quick random search (same deterministic physics as level_bot.py) finds a
fast winning plan, preferring plans that also grab the gem. The plan is then replayed frame by
frame (1/60 s physics steps, 30 fps video) in a clean view with every button hidden, followed by
a moment of the win celebration. The video opens on the static cover, as CrazyGames asks.
No sound. Needs Playwright + Edge, Pillow and ffmpeg.

    python world-shifter/tools/make_videos.py
    -> builds/crazygames-assets/preview-landscape-1920x1080.mp4, preview-portrait-1080x1620.mp4
"""
import json, pathlib, shutil, subprocess, sys
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import make_covers as mc  # same page setup and the cover renderer

OUT = mc.OUT
FPS, STEPS = 30, 2                  # 2 physics steps of 1/60 s per video frame
COVER_S, AFTER_WIN_S, MAX_S = 1.0, 1.1, 19.5
CLIPS = [180, 77, 220, 120]         # 0-based levels: underwater (the cover), pink candy, neon grid, blueprint
SIZES = {"landscape": (1920, 1080), "portrait": (1080, 1620)}

SEARCH_JS = r"""
([i, trials, seed]) => {
  window.__botQuiet = true; Storage.prototype.setItem = () => {}; saveStats = () => {}; frame = () => {};
  let s = seed >>> 0; const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  const DT = 1 / 60, MAX_T = 8;
  const randPlan = () => { const p = []; let t = 0; while (t < MAX_T) { const g = [Math.floor(rnd() * 3) - 1, 0.18 + rnd() * 0.9]; p.push(g); t += g[1]; } return p; };
  let best = null;
  for (let k = 0; k < trials; k++) {
    const plan = randPlan();
    loadLevel(i); freeze = 0; waiting = false; angVel = 0; keys.left = keys.right = false;
    let t = 0, seg = 0, segT = 0;
    while (t < MAX_T && state === "play") {
      while (seg < plan.length && segT >= plan[seg][1]) { segT -= plan[seg][1]; seg++; }
      const d = seg < plan.length ? plan[seg][0] : 0; keys.left = d < 0; keys.right = d > 0;
      update(DT); t += DT; segT += DT;
    }
    if (state === "won") {
      const gem = level.objs.some(o => o.t === "gem" && o.got);
      const score = t - (gem ? 3 : 0) + (t < 1.6 ? 2 : 0);  // prefer the gem; skip too-short wins (nothing to see)
      if (!best || score < best.score) best = { plan, t, gem, score };
    }
  }
  state = "paused"; keys.left = keys.right = false;
  return best;
}
"""

START_JS = r"""
([i, zoom, plan]) => {
  window.__p = { plan, seg: 0, segT: 0, post: false };
  loadLevel(i); freeze = 0; waiting = false; angVel = 0; keys.left = keys.right = false;
  level.view /= zoom;
  for (const el of document.body.children) if (el.tagName !== 'CANVAS' && el.tagName !== 'SCRIPT') el.style.visibility = 'hidden';
  window.__vt = performance.now();
}
"""
# exactly the search's control logic, step by step (being one 1/60 s step off on a control change
# is enough for a different run)
STEP_JS = r"""
(steps) => {
  const P = window.__p;
  for (let k = 0; k < steps && (state === "play" || P.post); k++) {
    while (P.seg < P.plan.length && P.segT >= P.plan[P.seg][1]) { P.segT -= P.plan[P.seg][1]; P.seg++; }
    const d = state === "play" && P.seg < P.plan.length ? P.plan[P.seg][0] : 0;
    keys.left = d < 0; keys.right = d > 0;
    update(1 / 60); P.segT += 1 / 60; window.__vt += 1000 / 60;
    if (state !== "play") P.post = true;
  }
  render(window.__vt);
  return state;
}
"""
# same as the covers: skip the little gravity marker
HIDE_MARKER = r"""
() => { const mt = ctx.moveTo, fl = ctx.fill; let skip = false;
  ctx.moveTo = function (x, y) { skip = x === W / 2 - 9 && y === H - 46; return mt.call(this, x, y); };
  ctx.fill = function (...a) { if (skip) { skip = false; return; } return fl.apply(this, a); }; }
"""


def plan_dir(plan, t):
    acc = 0
    for d, length in plan:
        if t < acc + length: return d
        acc += length
    return 0


def find_plans(pg):
    pg.set_viewport_size({"width": 600, "height": 600}); pg.goto(mc.GAME); pg.wait_for_timeout(500)
    plans = {}
    for lv in CLIPS:
        r = None
        for seed in (1, 2, 3):
            r = pg.evaluate(SEARCH_JS, [lv, 500, seed])
            if r: break
        print(f"level {lv + 1}: " + (f"win in {r['t']:.1f}s, gem {r['gem']}" if r else "no quick win, skipped"))
        if r: plans[lv] = r
    return plans


def record(pg, name, size, plans, frames_dir):
    if frames_dir.exists(): shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    n = 0
    # 1) the static cover as the opening frame
    cover = frames_dir / "cover.png"
    title = ("left:6%;top:50%;transform:translateY(-50%);font-size:170px;--k:14px;--d:10px" if name == "landscape"
             else "left:50%;top:5%;transform:translateX(-50%);font-size:172px;--k:14px;--d:10px")
    C = mc.COVER
    mc.shot(pg, size, C["level"], C["fall_ms"], C["tilt"], dx=330 if name == "landscape" else 0, dy=0 if name == "landscape" else 200,
            zoom=C["zoom"] * (1.3 if name == "landscape" else 1.0), title=title, path=cover)
    for _ in range(int(COVER_S * FPS)):
        shutil.copy(cover, frames_dir / f"{n:05d}.png"); n += 1
    # 2) the winning runs
    pg.set_viewport_size({"width": size[0], "height": size[1]}); pg.goto(mc.GAME); pg.wait_for_timeout(500)
    pg.evaluate("window.__botQuiet = true; Storage.prototype.setItem = () => {}; frame = () => {};")
    pg.evaluate(HIDE_MARKER)
    for lv, r in plans.items():
        if n / FPS > MAX_S - 2: break
        print(f"  {name}: level {lv + 1}", end="")
        pg.evaluate(START_JS, [lv, 1.15 if name == "landscape" else 1.0, r["plan"]])
        t, after = 0.0, 0
        while n / FPS < MAX_S and t < r["t"] + AFTER_WIN_S + 1:
            st = pg.evaluate(STEP_JS, STEPS); t += STEPS / 60
            pg.screenshot(path=str(frames_dir / f"{n:05d}.png")); n += 1
            if st != "play":
                after += 1
                if after >= AFTER_WIN_S * FPS: break
        print(f" -> {st}")
    out = OUT / f"preview-{name}-{size[0]}x{size[1]}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames_dir / "%05d.png"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(out)], check=True)
    print(f"{out.name}: {n / FPS:.1f}s, {out.stat().st_size / 1e6:.1f} MB")
    shutil.rmtree(frames_dir)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(); pg.add_init_script(mc.INIT)
        plans = find_plans(pg)
        for name, size in SIZES.items():
            record(pg, name, size, plans, OUT / f"_frames_{name}")
        b.close()


if __name__ == "__main__":
    main()

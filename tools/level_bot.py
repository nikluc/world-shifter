"""World Shifter level bot: is every level winnable *by a human*, and how hard is it?

1. Random play: thousands of random rotation plans at keyboard speed (slower than the touch
   dial). Controls are held for at least MIN_SEG seconds, like a person, not frame-perfect taps.
2. Human check: every winning plan is replayed JITTER_RUNS times with human-sized timing
   errors (reaction delay up to 0.15 s, about +-60 ms on every control change). A plan that only
   works when executed perfectly is "fragile". A level passes if some winning plan survives
   at least HUMAN_PASS of its sloppy replays.
3. If random play rarely wins, it explores like a player learning the level: it remembers every
   spot it reached (position + world angle) and keeps trying new moves from the least-explored
   ones, which finds multi-step routes (round a barricade, flip, come back).

Difficulty score = log10(attempts needed to find a win) + 2 x (1 - human robustness): higher is harder.

    python world-shifter/tools/level_bot.py [first] [last] [trials] [--paths sheet.png]
    (levels are 1-based; needs Playwright + Microsoft Edge; --paths also needs Pillow and draws
     each level with its most human-proof winning path, to spot shortcuts)
"""
import io, json, math, pathlib, sys
from playwright.sync_api import sync_playwright

HTML = pathlib.Path(__file__).resolve().parent.parent / "index.html"
HUMAN_PASS = 0.25

BOT_JS = r"""
([i, trials, climbIters, seed]) => {
  frame = () => {};                       // stop the game's own render loop
  let s = seed >>> 0;
  const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
  const MAX_T = 40, DT = 1 / 60, MIN_SEG = 0.18, JITTER = 0.06, JITTER_RUNS = 8, KEEP = 25;
  const randSeg = () => [Math.floor(rnd() * 3) - 1, MIN_SEG + rnd() * 1.0];
  const randPlan = () => { const p = []; let t = 0; while (t < MAX_T) { const g = randSeg(); p.push(g); t += g[1]; } return p; };

  function trial(plan, trace) {
    loadLevel(i); freeze = 0; waiting = false; angVel = 0; keys.left = keys.right = false;
    const goal = level.objs.find(o => o.t === "goal");
    let t = 0, seg = 0, segT = 0, minD = 1e9, f = 0;
    const path = trace ? [] : null;
    while (t < MAX_T) {
      while (seg < plan.length && segT >= plan[seg][1]) { segT -= plan[seg][1]; seg++; }
      const dir = seg < plan.length ? plan[seg][0] : 0;
      keys.left = dir < 0; keys.right = dir > 0;
      update(DT); t += DT; segT += DT;
      if (path && f++ % 3 === 0) path.push(Math.round(ball.x), Math.round(ball.y));
      if (state === "won") return { win: true, t: timer, minD: 0, path };
      if (state !== "play") return { win: false, t, minD, path };
      minD = Math.min(minD, Math.hypot(ball.x - goal.x, ball.y - goal.y));
    }
    return { win: false, t, minD, path };
  }
  // a human version of a plan: late start, and every control change a little early or late
  const sloppy = plan => [[0, rnd() * 0.15], ...plan.map(([d, len]) => [d, Math.max(0.05, len + gauss() * JITTER)])];
  const robustness = plan => { let w = 0; for (let k = 0; k < JITTER_RUNS; k++) if (trial(sloppy(plan)).win) w++; return w / JITTER_RUNS; };

  let wins = 0, best = null, bestScore = 1e9, bestScorePlan = null;
  const winners = [];
  for (let k = 0; k < trials; k++) {
    const p = randPlan(), r = trial(p);
    if (r.win) { wins++; if (!best || r.t < best) best = r.t; if (winners.length < KEEP) winners.push(p); }
    if (r.minD < bestScore) { bestScore = r.minD; bestScorePlan = p; }
  }
  // explore: like a player learning a level. Remember every spot reached (position + world angle)
  // with the controls that got there, then keep trying new moves from the least-explored spots.
  // Finds multi-step routes (go round a barricade, flip, come back) that random play never strings together.
  let climbed = false, exploreIters = 0;
  if (wins < 3) {
    const cells = new Map(), list = [];
    const cut = (plan, t) => { const out = []; let acc = 0; for (const [d, len] of plan) { if (acc + len >= t) { out.push([d, Math.max(0.01, t - acc)]); break; } out.push([d, len]); acc += len; } return out; };
    const visit = (plan, t) => {
      const a = ((angle % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
      const key = Math.floor(ball.x / 35) + "," + Math.floor(ball.y / 35) + "," + Math.floor(a / (Math.PI / 4));
      const c = cells.get(key);
      if (!c) { const n = { plan: cut(plan, t), t, sel: 0 }; cells.set(key, n); list.push(n); }
      else if (t < c.t - 0.05) { c.plan = cut(plan, t); c.t = t; }
    };
    function run(plan) { // play the plan only (no idle tail), recording cells
      loadLevel(i); freeze = 0; waiting = false; angVel = 0;
      const total = plan.reduce((a, g) => a + g[1], 0);
      let t = 0, seg = 0, segT = 0;
      while (t < total && t < MAX_T) {
        while (seg < plan.length && segT >= plan[seg][1]) { segT -= plan[seg][1]; seg++; }
        const dir = seg < plan.length ? plan[seg][0] : 0;
        keys.left = dir < 0; keys.right = dir > 0;
        update(DT); t += DT; segT += DT;
        if (state === "won") return { win: true, t: timer };
        if (state !== "play") return { win: false };
        visit(plan, t);
      }
      return { win: false };
    }
    run([[0, 0.5]]);
    for (; exploreIters < climbIters && winners.length < 3; exploreIters++) {
      let pick = list[Math.floor(rnd() * list.length)];
      for (let k = 0; k < 3; k++) { const c = list[Math.floor(rnd() * list.length)]; if (c.sel < pick.sel) pick = c; }
      pick.sel++;
      const plan = pick.plan.map(g => g.slice()), n = 1 + Math.floor(rnd() * 3);
      for (let k = 0; k < n; k++) plan.push(randSeg());
      const r = run(plan);
      if (r.win) { climbed = true; winners.push(plan); if (!best || r.t < best) best = r.t; }
    }
  }
  let robust = 0, robustSum = 0, robustPlan = null;
  for (const p of winners) { const r = robustness(p); robustSum += r; if (r > robust || !robustPlan) { robust = r; robustPlan = p; } }
  const path = robustPlan ? trial(robustPlan, true).path : null;
  state = "paused";
  // effort = how many attempts it took to find a win (random tries per win, or random + explore tries)
  const effort = wins >= 3 ? trials / wins : trials + exploreIters;
  return { level: i + 1, name: LEVELS[i].name, rate: wins / trials, best, climbed, closest: Math.round(bestScore),
           robust, robustAvg: winners.length ? robustSum / winners.length : 0, effort, path };
}
"""

# draw one level framed to fit its objects (and the path), with the path on top
SHEET_JS = r"""
([i, path, S]) => {
  loadLevel(i); state = "paused";
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  const add = (x, y) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); };
  for (const o of level.objs) { const r = Math.hypot(o.w, o.h) / 2 + Math.max(Math.abs((o.m || [0])[0]), Math.abs((o.m || [0, 0])[1])); add(o.x - r, o.y - r); add(o.x + r, o.y + r); }
  add(level.start[0], level.start[1]);
  if (path) for (let k = 0; k < path.length; k += 2) add(path[k], path[k + 1]);
  const view0 = level.view, cam0 = level.cam;
  level.view = Math.max(x1 - x0, y1 - y0) * 1.08; level.cam = "follow";
  cam = { x: (x0 + x1) / 2, y: (y0 + y1) / 2 };
  render(performance.now());
  const scale = Math.min(W, H) / level.view;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  ctx.translate(W / 2, H / 2); ctx.scale(scale, scale); ctx.translate(-cam.x, -cam.y);
  if (path) {
    ctx.strokeStyle = "#ffe14d"; ctx.lineWidth = 3 / scale * 1.4; ctx.globalAlpha = 0.9;
    ctx.beginPath(); ctx.moveTo(path[0], path[1]);
    for (let k = 2; k < path.length; k += 2) ctx.lineTo(path[k], path[k + 1]);
    ctx.stroke(); ctx.globalAlpha = 1;
  }
  level.view = view0; level.cam = cam0;
}
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sheet = sys.argv[sys.argv.index("--paths") + 1] if "--paths" in sys.argv else None
    if sheet in args:
        args.remove(sheet)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 300, "height": 300})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(HTML.as_uri())
        n = pg.evaluate("LEVELS.length")
        first = int(args[0]) if len(args) > 0 else 1
        last = int(args[1]) if len(args) > 1 else n
        trials = int(args[2]) if len(args) > 2 else 1500
        bad, results = 0, []
        for i in range(first - 1, last):
            r = pg.evaluate(BOT_JS, [i, trials, 6000, 12345 + i])
            ok = r["best"] is not None
            human = ok and r["robust"] >= HUMAN_PASS
            bad += not human
            # attempts needed to find a win, plus a penalty when wins only work with precise timing
            r["score"] = round(math.log10(max(r["effort"], 1)) + 2 * (1 - r["robustAvg"]), 2)
            results.append(r)
            tag = "OK  " if human else ("FRAGILE" if ok else "FAIL")
            best = f"{r['best']:.1f}s" if ok else "-"
            note = " (explored)" if r["climbed"] else ""
            print(f"{tag:<7} {r['level']:>2}. {r['name']:<20} solve {r['rate']*100:5.1f}%  human {r['robust']*100:3.0f}%  "
                  f"difficulty {r['score']:4.2f}  best {best}{note}", flush=True)
        print("page errors:", errs)
        if sheet:
            from PIL import Image, ImageDraw
            S, cols, imgs = 300, 6, []
            pg.evaluate("document.getElementById('hud').style.display='none'; document.getElementById('hint').style.display='none'")
            for r in results:
                pg.evaluate(SHEET_JS, [r["level"] - 1, r["path"], S])
                imgs.append((r, Image.open(io.BytesIO(pg.locator("#c").screenshot()))))
            rows = (len(imgs) + cols - 1) // cols
            out = Image.new("RGB", (cols * S, rows * S), "black")
            for k, (r, im) in enumerate(imgs):
                x, y = (k % cols) * S, (k // cols) * S
                out.paste(im.resize((S, S)), (x, y))
                ImageDraw.Draw(out).text((x + 6, y + 6), f"{r['level']}. {r['name']}  d{r['score']}", fill="yellow")
            out.save(sheet)
        json.dump([{k: v for k, v in r.items() if k != "path"} for r in results],
                  open(pathlib.Path(__file__).parent / "last_bot_run.json", "w"), indent=1)
        b.close()
        sys.exit(1 if bad or errs else 0)


if __name__ == "__main__":
    main()

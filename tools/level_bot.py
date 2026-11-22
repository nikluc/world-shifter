"""World Shifter level bot: checks every level is winnable and measures difficulty.

Plays each level headlessly with random keyboard-speed rotation plans (slower than the
touch dial, so a pass here is conservative), then hill-climbs on distance-to-goal if
random play never wins.  Reports random solve rate (difficulty) and best time.

    python world-shifter/tools/level_bot.py [first_level] [last_level] [trials]
    (levels are 1-based; needs Playwright + Microsoft Edge)
"""
import json, pathlib, sys
from playwright.sync_api import sync_playwright

HTML = pathlib.Path(__file__).resolve().parent.parent / "index.html"

BOT_JS = r"""
([i, trials, climbIters, seed]) => {
  frame = () => {};                       // stop the game's own render loop
  let s = seed >>> 0;
  const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  const MAX_T = 40, DT = 1 / 60;
  const randSeg = () => [Math.floor(rnd() * 3) - 1, 0.1 + rnd() * 1.1];
  const randPlan = () => { const p = []; let t = 0; while (t < MAX_T) { const g = randSeg(); p.push(g); t += g[1]; } return p; };

  function trial(plan) {
    loadLevel(i); freeze = 0; waiting = false; angVel = 0; keys.left = keys.right = false;
    const goal = level.objs.find(o => o.t === "goal");
    let t = 0, seg = 0, segT = 0, minD = 1e9;
    while (t < MAX_T) {
      while (seg < plan.length && segT >= plan[seg][1]) { segT -= plan[seg][1]; seg++; }
      const dir = seg < plan.length ? plan[seg][0] : 0;
      keys.left = dir < 0; keys.right = dir > 0;
      update(DT); t += DT; segT += DT;
      if (state === "won") return { win: true, t: timer, minD: 0 };
      if (state !== "play") return { win: false, t, minD };
      minD = Math.min(minD, Math.hypot(ball.x - goal.x, ball.y - goal.y));
    }
    return { win: false, t, minD };
  }

  let wins = 0, best = null, bestPlan = null, bestScore = 1e9, bestScorePlan = null;
  for (let k = 0; k < trials; k++) {
    const p = randPlan(), r = trial(p);
    if (r.win) { wins++; if (!best || r.t < best) best = r.t; }
    if (r.minD < bestScore) { bestScore = r.minD; bestScorePlan = p; }
  }
  let climbed = false;
  if (!wins) { // hill-climb: mutate the plan that got closest to the goal
    let cur = bestScorePlan, curScore = bestScore;
    for (let k = 0; k < climbIters && !best; k++) {
      const p = cur.map(g => g.slice()), j = Math.floor(rnd() * p.length);
      if (rnd() < 0.5) p[j] = randSeg(); else for (let m = j; m < p.length; m++) p[m] = randSeg();
      const r = trial(p);
      if (r.win) { best = r.t; climbed = true; break; }
      if (r.minD <= curScore) { cur = p; curScore = r.minD; }
    }
    bestScore = Math.min(bestScore, curScore);
  }
  state = "paused";
  return { level: i + 1, name: LEVELS[i].name, rate: wins / trials, best, climbed, closest: Math.round(bestScore) };
}
"""


def main():
    a = sys.argv[1:]
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(HTML.as_uri())
        n = pg.evaluate("LEVELS.length")
        first = int(a[0]) if len(a) > 0 else 1
        last = int(a[1]) if len(a) > 1 else n
        trials = int(a[2]) if len(a) > 2 else 1500
        bad = 0
        for i in range(first - 1, last):
            r = pg.evaluate(BOT_JS, [i, trials, 6000, 12345 + i])
            ok = r["best"] is not None
            bad += not ok
            best = f"{r['best']:.1f}s" if ok else "-"
            tag = "OK " if ok else "FAIL"
            note = " (needed hill-climb)" if r["climbed"] else ("" if ok else f" closest {r['closest']}")
            print(f"{tag} {r['level']:>2}. {r['name']:<22} solve {r['rate']*100:5.1f}%  best {best}{note}", flush=True)
        print("page errors:", errs)
        b.close()
        sys.exit(1 if bad or errs else 0)


if __name__ == "__main__":
    main()

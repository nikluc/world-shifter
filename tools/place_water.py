"""Add water pools to generated levels: where the ball falls fast on the bot's winning route,
clear of walls, spikes, the start and the goal, and only if the level stays winnable by a human.

For each chosen level: explore it with the level bot to get a human-proof winning route, measure
the ball's speed along it, try pools centred on the fastest stretches (a few sizes), and accept the
first pool where the bot still wins with at least level_bot.HUMAN_PASS of sloppy replays and the
level does not become a no-input "lazy" win. Results go to water.json ({level name: [x, y, w, h]})
after every level; the game applies them from its WATER table (genLevel stays untouched).

    python world-shifter/tools/place_water.py [first] [last] [--every N] [--part K/N] [--out file.json]
    (1-based levels, default 241..500, every 3rd generated level; --part K/N takes every Nth of those,
     so N copies can run in parallel, each with its own --out file)
"""
import json, pathlib, sys, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from level_bot import BOT_JS, HUMAN_PASS, GEM_PASS, HTML

SIZES = [(200, 160), (160, 220), (260, 140), (150, 150), (120, 120), (100, 170)]

CANDS_JS = r"""
([i, path, sizes]) => {
  loadLevel(i); state = "paused"; placeObjs(0);
  const solids = level.objs.filter(o => o.t !== "gem" && o.t !== "water");
  const goal = solids.find(o => o.t === "goal");
  const dist = (o, x, y) => { const dx = x - o.x, dy = y - o.y, lx = dx * o._c + dy * o._s, ly = -dx * o._s + dy * o._c;
    return Math.hypot(Math.max(Math.abs(lx) - o.w / 2, 0), Math.max(Math.abs(ly) - o.h / 2, 0)); };
  const pts = []; for (let k = 0; path && k + 3 < path.length; k += 2) pts.push([path[k], path[k + 1], Math.hypot(path[k + 2] - path[k], path[k + 3] - path[k + 1]) / 0.05]);
  const fast = pts.filter(([x, y, v]) => v > 300 && Math.hypot(x - level.start[0], y - level.start[1]) > 110 && dist(goal, x, y) > 110)
                  .sort((a, b) => b[2] - a[2]);
  const out = [];
  for (const [x, y, v] of fast) {
    if (out.some(c => Math.hypot(c[0] - x, c[1] - y) < 120)) continue;
    for (const [w, h] of sizes) {
      const cx = Math.round(x / 10) * 10, cy = Math.round(y / 10) * 10;
      // a pool may run under walls a little (it is drawn behind them) but not over the goal or spikes
      let ok = true, blocked = 0, total = 0;
      for (let a = -0.5; a <= 0.5 && ok; a += 0.125) for (let b = -0.5; b <= 0.5 && ok; b += 0.125) {
        const px = cx + a * w, py = cy + b * h; total++;
        for (const o of solids) {
          const d = dist(o, px, py);
          if ((o.t === "goal" || o.t === "spike" || o.t === "portal") && d < 8) { ok = false; break; }
          if (d < 4) { blocked++; break; }
        }
        if (Math.hypot(px - level.start[0], py - level.start[1]) < 50) ok = false;
        if (level.bounds && Math.hypot(px, py) > level.bounds - 20) ok = false;
      }
      if (blocked > total * 0.3) ok = false;
      if (ok) { out.push([cx, cy, w, h, Math.round(v)]); break; }
    }
    if (out.length >= 6) break;
  }
  return out;
}
"""
SET_WATER_JS = r"""
([i, r]) => {
  const objs = LEVELS[i].objs;
  for (let k = objs.length - 1; k >= 0; k--) if (objs[k].t === "water") objs.splice(k, 1);
  if (r) objs.unshift({ x: r[0], y: r[1], w: r[2], h: r[3], t: "water" });
}
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 3
    part = sys.argv[sys.argv.index("--part") + 1] if "--part" in sys.argv else "1/1"
    out_file = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else pathlib.Path(__file__).parent / "water.json"
    for flag in ("--every", "--part", "--out"):
        if flag in sys.argv:
            v = sys.argv[sys.argv.index(flag) + 1]
            if v in args: args.remove(v)
    k_part, n_part = map(int, part.split("/"))
    placed = json.loads(out_file.read_text()) if out_file.exists() else {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 300, "height": 300})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(HTML.as_uri())
        n = pg.evaluate("LEVELS.length")
        first = int(args[0]) if args else 241
        last = int(args[1]) if len(args) > 1 else n
        gen = [i for i in range(first - 1, last) if pg.evaluate(f"!!LEVELS[{i}].gen")]
        chosen = gen[::every][k_part - 1::n_part]
        print(f"[{time.strftime('%H:%M:%S')}] part {part}: {len(chosen)} levels", flush=True)
        for i in chosen:
            t0 = time.time()
            name = pg.evaluate(f"LEVELS[{i}].name")
            if name in placed:
                continue
            pg.evaluate(SET_WATER_JS, [i, None])
            base = pg.evaluate(BOT_JS, [i, 600, 2500, 4242 + i, {"timeLimit": 90}])
            has_gem = pg.evaluate(f"LEVELS[{i}].objs.some(o => o.t === 'gem')")
            got = None
            if base["best"] is not None and base["path"]:
                cands = pg.evaluate(CANDS_JS, [i, base["path"], SIZES])
                for c in cands:
                    pg.evaluate(SET_WATER_JS, [i, c[:4]])
                    r = pg.evaluate(BOT_JS, [i, 800, 4000, 777 + i, {"lazy": True, "timeLimit": 90}])
                    if r["best"] is not None and r["robust"] >= HUMAN_PASS and not r["lazy"]:
                        if has_gem:  # the level's gem must stay collectable with the pool in place
                            g = pg.evaluate(BOT_JS, [i, 800, 4000, 555 + i, {"gem": True, "timeLimit": 90}])
                            if g["best"] is None or g["robust"] < GEM_PASS:
                                continue
                        got = c + [round(r["robust"], 2), round(r["best"], 1)]; break
            pg.evaluate(SET_WATER_JS, [i, None])
            dt = time.time() - t0
            if got:
                placed[name] = got[:4]
                print(f"[{time.strftime('%H:%M:%S')}] {i + 1:>3}. {name:<20} water {got[2]}x{got[3]} at ({got[0]},{got[1]}) speed {got[4]}  human {got[5] * 100:3.0f}%  best {got[6]}s  ({dt:.0f}s)", flush=True)
            else:
                placed[name] = None
                print(f"[{time.strftime('%H:%M:%S')}] {i + 1:>3}. {name:<20} no pool fits ({dt:.0f}s)", flush=True)
            out_file.write_text(json.dumps(placed, indent=1))
        print(f"[{time.strftime('%H:%M:%S')}] DONE part {part}; page errors: {errs}", flush=True)
        b.close()


if __name__ == "__main__":
    main()

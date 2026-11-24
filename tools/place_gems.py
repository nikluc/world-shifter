"""Place one gem per level: off the normal route, close to danger, and provably collectable.

For each level: explore it with the level bot and record every spot the ball can reach, score
those spots (far from the bot's winning route = a detour, near spikes = risky, clear of walls,
away from start and goal), then try the best ones in order. A spot is accepted only if the bot
can win *with the gem* and that win survives sloppy human timing: at least 50% of sloppy
replays early on (levels 1-20), 25% mid-game (21-40), level_bot.GEM_PASS late (41+).

    python world-shifter/tools/place_gems.py [first] [last] [--missing] [--write]
    (1-based levels; without --write it only prints/saves gems.json; --write puts the gems into
     index.html, replacing any existing gem in those levels; --missing skips levels that already have one)
"""
import json, pathlib, re, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from level_bot import BOT_JS, GEM_PASS, HTML

GEM = 26  # gem size (world units)

SCORE_JS = r"""
([i, spots, path, gemSize, near]) => {
  loadLevel(i); state = "paused"; placeObjs(0);
  const objs = level.objs.filter(o => o.t !== "gem");
  const goal = objs.find(o => o.t === "goal");
  const dist = (o, x, y) => { // point to rotated rectangle surface (0 inside)
    const dx = x - o.x, dy = y - o.y, lx = dx * o._c + dy * o._s, ly = -dx * o._s + dy * o._c;
    return Math.hypot(Math.max(Math.abs(lx) - o.w / 2, 0), Math.max(Math.abs(ly) - o.h / 2, 0));
  };
  const route = [];
  for (let k = 0; path && k < path.length; k += 2) route.push([path[k], path[k + 1]]);
  const out = [];
  for (const [x, y] of spots) {
    let clear = 1e9, dSpike = 1e9, dPortal = 1e9;
    for (const o of objs) {
      const d = dist(o, x, y);
      if (o.t === "spike") dSpike = Math.min(dSpike, d);
      if (o.t === "portal") dPortal = Math.min(dPortal, d);
      if (o.t !== "goal") clear = Math.min(clear, d);
    }
    const dStart = Math.hypot(x - level.start[0], y - level.start[1]);
    const dGoal = dist(goal, x, y);
    const dRoute = route.length ? Math.min(...route.map(([px, py]) => Math.hypot(px - x, py - y))) : 300;
    if (clear < gemSize * 0.6 || dPortal < 40 || dStart < 120 || dGoal < 90) continue;
    if (level.bounds && Math.hypot(x, y) > level.bounds - 50) continue;
    // normal: reward a detour. near (fallback): a risky spot just off the usual line
    const detour = near ? Math.max(0, 1 - Math.abs(dRoute - 70) / 90) : Math.min(dRoute / 220, 1);
    const risk = dSpike > 1e8 ? 0 : Math.max(0, 1 - Math.abs(dSpike - 35) / 70);
    out.push({ x: Math.round(x), y: Math.round(y), score: 0.6 * detour + 0.4 * risk, dRoute: Math.round(dRoute), dSpike: Math.round(Math.min(dSpike, 9999)) });
  }
  out.sort((a, b) => b.score - a.score);
  const picks = []; // best few, spread out
  for (const c of out) { if (picks.every(p => Math.hypot(p.x - c.x, p.y - c.y) > 90)) picks.push(c); if (picks.length >= 10) break; }
  return picks;
}
"""
SET_GEM_JS = r"""
([i, x, y, s]) => {
  const objs = LEVELS[i].objs;
  for (let k = objs.length - 1; k >= 0; k--) if (objs[k].t === "gem") objs.splice(k, 1);
  if (x !== null) objs.push({ x, y, w: s, h: s, t: "gem" });
}
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    missing = "--missing" in sys.argv
    out_file = pathlib.Path(__file__).parent / "gems.json"
    placed = json.loads(out_file.read_text()) if out_file.exists() else {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page()
        pg.goto(HTML.as_uri())
        n = pg.evaluate("LEVELS.length")
        first = int(args[0]) if args else 1
        last = int(args[1]) if len(args) > 1 else n
        for i in range(first - 1, last):
            name = pg.evaluate(f"LEVELS[{i}].name")
            if missing and name in placed:
                continue
            pg.evaluate(SET_GEM_JS, [i, None, None, GEM])
            ex = pg.evaluate(BOT_JS, [i, 600, 2500, 777 + i, {"explore": True}])
            need = 0.5 if i < 20 else 0.25 if i < 40 else GEM_PASS  # gems get harder as you go
            got, fallback = None, None
            for near in (False, True):  # detour spots first, then risky spots near the usual line
                cands = pg.evaluate(SCORE_JS, [i, ex["spots"] or [], ex["path"], GEM, near])
                for c in cands:
                    pg.evaluate(SET_GEM_JS, [i, c["x"], c["y"], GEM])
                    r = pg.evaluate(BOT_JS, [i, 800, 4000, 999 + i, {"gem": True}])
                    if r["best"] is None:
                        continue
                    if r["robust"] >= need:
                        got = dict(c, robust=r["robust"]); break
                    if r["robust"] >= GEM_PASS and (not fallback or r["robust"] > fallback["robust"]):
                        fallback = dict(c, robust=r["robust"])
                if got:
                    break
            got = got or fallback
            pg.evaluate(SET_GEM_JS, [i, None, None, GEM])
            if got:
                placed[name] = [got["x"], got["y"]]
                print(f"{i + 1:>2}. {name:<20} gem at ({got['x']:>5}, {got['y']:>5})  off-route {got['dRoute']:>4}  "
                      f"to spikes {got['dSpike'] if got['dSpike'] < 9999 else '-':>4}  human {got['robust'] * 100:3.0f}%", flush=True)
            else:
                print(f"{i + 1:>2}. {name:<20} no safe-to-prove gem spot found ({len(cands)} candidates)", flush=True)
        b.close()
    out_file.write_text(json.dumps(placed, indent=1))
    if write:
        s = HTML.read_text(encoding="utf-8")
        for name, (x, y) in placed.items():
            m = re.search(r'  \{ name: "' + re.escape(name) + r'".*?\n    \] \},\n', s, re.S)
            c = re.sub(r'      \{ x: [-\d]+, y: [-\d]+, w: \d+, h: \d+, t: "gem" \},\n', "", m.group(0))
            c = c[: c.rindex("    ] },")] + f'      {{ x: {x}, y: {y}, w: {GEM}, h: {GEM}, t: "gem" }},\n    ] }},\n'
            s = s[: m.start()] + c + s[m.end():]
        HTML.write_text(s, encoding="utf-8", newline="")
        print(f"wrote {len(placed)} gems into index.html")


if __name__ == "__main__":
    main()

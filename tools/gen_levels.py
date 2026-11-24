"""Grow World Shifter to N levels with generated ones, keeping only levels a human can win.

Step 1 (search): many seeds, in parallel. Each seed becomes a recipe [type, seed, difficulty, par]
built by genLevel() in index.html, then the level bot plays it. Kept only if:
  - the bot can win it and a winning plan survives sloppy human timing (robust >= 25%)
  - no single fixed tilt wins it (lazy test: no trivial levels, no straight-line shortcuts)
The 60 hand-made levels are scored the same way, so everything shares one difficulty scale.

Step 2 (build): pick generated levels spread evenly over the difficulty range, merge them with
the hand-made ones, sort by difficulty (World's End last),
and write the result into index.html as RUN. Mechanics unlock at fixed points (UNLOCK), each with
its hand-made intro level; nothing uses a mechanic before its intro.

    python world-shifter/tools/gen_levels.py search --seeds 1-3000 --workers 10
    python world-shifter/tools/gen_levels.py build --total 500
    python world-shifter/tools/gen_levels.py addgems gems_gen*.json   (after place_gems.py --gen-only)
"""
import json, math, pathlib, random, subprocess, sys
TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from level_bot import BOT_JS, HTML

RESULTS = TOOLS / "gen_results.jsonl"
TYPES = [("room", 0.4), ("void", 0.25), ("tower", 0.2), ("corridor", 0.15)]
TRIALS, EXPLORE = 500, 3000
INTRO = {"moving": "Slider", "bounce": "Bounce Gap", "glue": "Sticky Start", "ice": "Black Ice", "portal": "First Portal"}
UNLOCK = {"moving": 8, "bounce": 25, "glue": 60, "ice": 110, "portal": 170}  # level number (for a 500-level run)

MECH_JS = """i => { const l = LEVELS[i]; return {
  moving: l.objs.some(o => o.m || o.spin), bounce: l.objs.some(o => o.t === "bounce"),
  glue: l.objs.some(o => o.t === "glue"), ice: l.objs.some(o => o.t === "ice"),
  portal: l.objs.some(o => o.t === "portal") }; }"""


def recipe(seed):
    rnd = random.Random(seed)
    x, acc = rnd.random(), 0
    for t, w in TYPES:
        acc += w
        if x <= acc:
            break
    return [t, seed, round(rnd.random(), 2), 10]


def evaluate(pg, i, seed):
    r = pg.evaluate(BOT_JS, [i, TRIALS, EXPLORE, 4242 + seed, {"lazy": True, "keep": 6}])
    score = round(math.log10(max(r["effort"], 1)) + 2 * (1 - r["robustAvg"]), 2)
    return {"name": r["name"], "solved": r["best"] is not None, "best": r["best"], "robust": r["robust"],
            "robustAvg": r["robustAvg"], "lazy": r["lazy"], "score": score, "mech": pg.evaluate(MECH_JS, i)}


def worker(seeds, out_path, hand):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p, open(out_path, "a") as out:
        b = p.chromium.launch(channel="msedge"); pg = b.new_page(); pg.goto(HTML.as_uri())
        pg.evaluate("frame = () => {}")
        if hand:  # score the hand-made levels on the same scale (each is pushed on the end and popped)
            for h in range(pg.evaluate("HAND_LEVELS.length")):
                i = pg.evaluate(f"(LEVELS.push(HAND_LEVELS[{h}]), LEVELS.length - 1)")
                res = evaluate(pg, i, 100000 + h)
                pg.evaluate("LEVELS.pop()")
                out.write(json.dumps(dict(res, hand=True)) + "\n"); out.flush()
        for seed in seeds:
            spec = recipe(seed)
            i = pg.evaluate("sp => { LEVELS.push(genLevel(sp)); return LEVELS.length - 1; }", spec)
            try:
                res = evaluate(pg, i, seed)
            except Exception as e:  # a broken recipe must not stop the search
                res = {"error": str(e)[:200]}
            pg.evaluate("LEVELS.pop()")
            out.write(json.dumps(dict(res, spec=spec)) + "\n"); out.flush()
        b.close()


def search(seed_range, workers):
    a, z = map(int, seed_range.split("-"))
    seeds = list(range(a, z + 1))
    procs = []
    for k in range(workers):
        part = TOOLS / f"gen_part{k}.jsonl"
        part.unlink(missing_ok=True)
        args = [sys.executable, __file__, "_worker", ",".join(map(str, seeds[k::workers])), str(part), "hand" if k == 0 else "-"]
        procs.append((subprocess.Popen(args), part))
    for pr, _ in procs:
        pr.wait()
    with open(RESULTS, "a") as out:
        for _, part in procs:
            out.write(part.read_text()); part.unlink()
    print("search done:", sum(1 for _ in open(RESULTS)), "results in", RESULTS.name)


def build(total):
    rows = [json.loads(l) for l in open(RESULTS) if l.strip()]
    hand = {r["name"]: r for r in rows if r.get("hand")}
    gen_all = [r for r in rows if not r.get("hand") and r.get("solved") and r["robust"] >= 0.25 and r["lazy"] is False]
    taken, gen = set(hand), []
    for r in sorted(gen_all, key=lambda r: r["spec"][1]):   # unique names, hand-made names reserved
        if r["name"] not in taken:
            taken.add(r["name"]); gen.append(r)
    need = total - len(hand)
    print(f"{len(rows)} results: {len(gen)} usable generated levels for {need} slots")
    gen.sort(key=lambda r: r["score"])
    if len(gen) > need:  # spread picks evenly across the difficulty range
        gen = [gen[round(k * (len(gen) - 1) / (need - 1))] for k in range(need)]
    for r in gen:
        r["spec"][3] = max(4, round((r["best"] or 4) * 2.5))
    entries = [(r["score"], r["name"], r["spec"], r["mech"]) for r in gen]
    entries += [(r["score"], n, n, r["mech"]) for n, r in hand.items()]
    entries.sort(key=lambda e: e[0])
    # pacing: each mechanic unlocks at a fixed level number with its hand-made intro level; before that,
    # only levels without it can be placed. At every slot the easiest eligible level goes next.
    unlock = {m: round(pos * total / 500) for m, pos in UNLOCK.items()}
    pinned = {unlock[m]: intro for m, intro in INTRO.items()}
    pool = [e for e in entries if e[1] not in ("Steer the Fall", "World's End") and e[1] not in INTRO.values()]
    byname = {e[1]: e for e in entries}
    order = [byname["Steer the Fall"]]
    while len(order) < total - 1:
        pos = len(order) + 1
        if pos in pinned:
            order.append(byname[pinned[pos]]); continue
        ok = [e for e in pool if all(pos > unlock[m] for m, used in e[3].items() if used)]
        e = min(ok or pool, key=lambda e: e[0])
        pool.remove(e); order.append(e)
    order.append(byname["World's End"])
    run = [e[2] for e in order]
    s = HTML.read_text(encoding="utf-8")
    start = s.index("const RUN = "); end = s.index(";\n", start) + 2
    body = ",\n  ".join(json.dumps(x, ensure_ascii=False) for x in run)
    s = s[:start] + f"const RUN = [\n  {body},\n];\n" + s[end:]
    HTML.write_text(s, encoding="utf-8", newline="")
    print(f"wrote RUN: {len(run)} levels ({len(hand)} hand-made, {len(gen)} generated)")
    for k in range(0, len(order), max(1, len(order) // 20)):
        print(f"  {k + 1:>3}. {order[k][1]:<20} d{order[k][0]:.2f}")


def addgems(files):
    """Store gem positions (from place_gems.py --gen-only --out ...) in the generated recipes in RUN."""
    from playwright.sync_api import sync_playwright
    placed = {}
    for f in files:
        placed.update(json.loads(pathlib.Path(f).read_text()))
    s = HTML.read_text(encoding="utf-8")
    start = s.index("const RUN = ["); end = s.index("];\n", start) + 3
    run = json.loads("[" + s[start + len("const RUN = ["): end - 3].strip().rstrip(",") + "]")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge"); pg = b.new_page(); pg.goto(HTML.as_uri())
        names = pg.evaluate("RUN.map(e => typeof e === 'string' ? e : genLevel(e).name)")
        b.close()
    n = 0
    for k, e in enumerate(run):
        if isinstance(e, list):
            e[:] = e[:4] + ([placed[names[k]]] if names[k] in placed else [])
            n += names[k] in placed
    body = ",\n  ".join(json.dumps(x, ensure_ascii=False) for x in run)
    HTML.write_text(s[:start] + f"const RUN = [\n  {body},\n];\n" + s[end:], encoding="utf-8", newline="")
    print(f"stored gems in {n} generated levels")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "_worker":
        worker([int(x) for x in sys.argv[2].split(",") if x], sys.argv[3], sys.argv[4] == "hand")
    elif cmd == "search":
        search(sys.argv[sys.argv.index("--seeds") + 1], int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 8)
    elif cmd == "addgems":
        addgems(sys.argv[2:])
    elif cmd == "build":
        build(int(sys.argv[sys.argv.index("--total") + 1]) if "--total" in sys.argv else 500)

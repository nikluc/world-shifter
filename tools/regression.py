"""World Shifter regression suite: one run, every feature that broke or could break before.

    python world-shifter/tools/regression.py            (needs Playwright + Microsoft Edge)
    python world-shifter/tools/regression.py --perf     (also: frame times on a 6x-slowed CPU)

Prints PASS/FAIL per check and exits 1 on any failure or page error. Each check starts from a clean
save (localStorage cleared) so they don't depend on each other. Uses a local web server on port 8790
for the parts that need http (2-player page, update check).
"""
import json, pathlib, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8790
BASE = f"http://localhost:{PORT}/index.html"
SEEN = json.dumps({k: 1 for k in ["moving", "bounce", "glue", "ice", "portal", "gem", "water", "moon", "underwater"]})
FAILS, ERRS = [], []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra not in ("", None) else ""), flush=True)
    if not ok:
        FAILS.append(name)


def fresh(ctx, query="", econ=None, extra_js=""):
    """A page with a clean save: tutorial cards seen, today's gift claimed (so no popup), optional econ."""
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: ERRS.append(str(e)))
    e = econ or {"wallet": 50}
    init = (f"if(!sessionStorage.getItem('rt')){{sessionStorage.setItem('rt',1);localStorage.clear();"
            f"localStorage.setItem('ws_seen',{json.dumps(SEEN)});"
            f"const e={json.dumps(e)};e.gift=e.gift||{{last:new Date().toLocaleDateString('sv'),step:0}};"
            f"localStorage.setItem('ws_econ',JSON.stringify(e));{extra_js}}}")
    pg.add_init_script(init)
    pg.goto(BASE + query)
    pg.wait_for_timeout(400)
    return pg


GO = "hide('menu'); hide('gift'); hide('card'); waiting = false; freeze = 0; state = 'play';"
WIN_AT_GOAL = "const g = level.objs.find(o => o.t === 'goal'); ball.x = g.x; ball.y = g.y; ball.vx = 0; ball.vy = 0;"


def suite(b):
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True)

    # ---- boot, levels, worlds ----
    pg = fresh(ctx)
    info = pg.evaluate("[LEVELS.length, WORLD_SIZES.slice(0, 6).join(','), worldCount(), WORLD_SIZES.reduce((a, b) => a + b, 0), isShown('menu')]")
    check("boot: 500 levels, worlds 5,8,10,12,15,20..., menu shown", info[0] == 500 and info[1] == "5,8,10,12,15,20" and info[3] == 500 and info[4], info)
    check("special worlds: ~88 physics levels, water pools present",
          pg.evaluate("LEVELS.filter(L => L.phys).length") >= 80 and pg.evaluate("LEVELS.filter(L => L.objs.some(o => o.t === 'water')).length") >= 40)
    res = pg.evaluate("""(() => { const orig = buildLevels(); let bad = 0;
      const inside = (o, x, y) => { const a = (o.a||0)*Math.PI/180, c = Math.cos(a), s = Math.sin(a), dx = x-o.x, dy = y-o.y; return Math.abs(dx*c+dy*s) <= o.w/2+14 && Math.abs(-dx*s+dy*c) <= o.h/2+14; };
      LEVELS.forEach((L, i) => { const A = orig[i].objs.filter(o => o.t === 'spike'), B = L.objs.filter(o => o.t === 'spike'); if (A.length === B.length) return;
        for (const o of A) for (let k = 0; k < 40; k++) { const x = o.x + (Math.random()-0.5)*(o.w+60), y = o.y + (Math.random()-0.5)*(o.h+60); if (A.some(q => inside(q,x,y)) !== B.some(q => inside(q,x,y))) bad++; } });
      return [SPIKES_MERGED, bad]; })()""")
    check("merged spikes cover exactly the original area", res[1] == 0 and res[0] > 0, res)

    # ---- win: stars, popup, celebration, progress ----
    pg.evaluate("loadLevel(1);" + GO + "timer = 0.5;" + WIN_AT_GOAL)
    pg.wait_for_timeout(2600)
    check("win: popup + 3 stars saved + landing fx", pg.evaluate("isShown('win') && progress[LEVELS[1].name] === 3 && document.querySelectorAll('#winStars i.on').length === 3"))
    # ---- death: shards, quip, slow-mo, retry ----
    pg.evaluate("hide('win'); loadLevel(0);" + GO + "const s = level.objs.find(o => o.t === 'spike'); ball.x = s.x; ball.y = s.y;")
    pg.wait_for_timeout(150)
    check("death: shards + quip + slow-mo", pg.evaluate("state === 'dead' && particles.some(p => p.shard) && floaters.length > 0 && !!slowmo"))
    pg.wait_for_timeout(1500)
    check("death: retry after slow-mo", pg.evaluate("state === 'play' && deaths.n === 1"))

    # ---- gem: collected, flies to HUD, fireworks, paid on win ----
    w0 = pg.evaluate("econ.wallet")
    pg.evaluate("loadLevel(1);" + GO + "const g = level.objs.find(o => o.t === 'gem'); ball.x = g.x; ball.y = g.y; ball.vx = 0; ball.vy = 0;")
    pg.wait_for_timeout(200)
    check("gem: fly-to-HUD + fireworks", pg.evaluate("!!document.querySelector('.flygem') && fireworks.length > 0"))
    pg.evaluate("timer = 0.5;" + WIN_AT_GOAL)
    pg.wait_for_timeout(900)
    check("gem: +10 ◆ on win", pg.evaluate("econ.wallet") - w0 >= 10, pg.evaluate("econ.wallet") - w0)
    pg.close()

    # ---- world complete: chest with a skin, combo ----
    pg = fresh(ctx)
    pg.evaluate("progress = {}; for (let i = 0; i < 4; i++) progress[LEVELS[i].name] = 3; econ.combo = 0;")
    s0, w0 = pg.evaluate("econ.skins.length"), pg.evaluate("econ.wallet")
    pg.evaluate("loadLevel(4);" + GO + "timer = 0.3;" + WIN_AT_GOAL)
    pg.wait_for_timeout(2900)
    check("world chest: opens, skin + 20 ◆ granted", pg.evaluate("isShown('chest')") and pg.evaluate("econ.skins.length") == s0 + 1 and pg.evaluate("econ.wallet") - w0 >= 20)
    pg.click("#chestWrap"); pg.wait_for_timeout(2000)
    check("world chest: reveal shows tier + skin", pg.evaluate("document.getElementById('chestWrap').classList.contains('shown') && document.getElementById('chestTier').textContent.endsWith('!')"))
    pg.click("#bChestOk"); pg.wait_for_timeout(200)
    check("world chest: closes back to results", pg.evaluate("!isShown('chest') && isShown('win')"))
    odds = pg.evaluate("(() => { econ.skins = ['classic']; const c = [0,0,0,0]; for (let i = 0; i < 1000; i++) c[pickChestSkin(0).tier]++; return c; })()")
    check("chest odds world 1 ≈ 70/25/5/0", 600 < odds[0] < 800 and odds[3] == 0, odds)
    pg.close()

    # ---- pending chests from earlier runs ----
    names = None
    pg = fresh(ctx)
    names = pg.evaluate("LEVELS.slice(0, 13).map(l => l.name)")
    pg.close()
    stars = json.dumps(json.dumps({n: 3 for n in names}))
    pg = fresh(ctx, econ={"wallet": 0, "chests": {"0": True}}, extra_js=f"localStorage.setItem('ws_stars',{stars});")
    check("pending chests: 2 waiting, gift popup at start", pg.evaluate("pendingChests().length === 2 && isShown('gift')"))
    pg.click("#bOpenChest"); pg.wait_for_timeout(900); pg.click("#chestWrap"); pg.wait_for_timeout(2000); pg.click("#bChestOk"); pg.wait_for_timeout(300)
    pg.click("#bOpenChest"); pg.wait_for_timeout(900); pg.click("#chestWrap"); pg.wait_for_timeout(2000); pg.click("#bChestOk"); pg.wait_for_timeout(300)
    check("pending chests: world 1 skin only, world 2 skin + 20 ◆", pg.evaluate("pendingChests().length === 0 && econ.wallet === 20 && econ.skins.length === 3"),
          pg.evaluate("[econ.wallet, econ.skins.length]"))
    pg.close()

    # ---- level builder: build, clear rule, code round trip ----
    pg = fresh(ctx)
    pg.evaluate("openMenu('build')"); pg.click("#bNewLevel"); pg.wait_for_timeout(200)
    pg.click("#edPal button:has-text('Spikes')"); pg.click("#edPal button:has-text('Water')")
    check("builder: pieces added, not cleared, share blocked", pg.evaluate("ed.objs.length === 4 && !isCleared(ed)"))
    pg.click("#edTest"); pg.wait_for_timeout(300)
    pg.evaluate(GO + "timer = 2.2;" + WIN_AT_GOAL); pg.wait_for_timeout(1600)
    check("builder: beating it clears it", pg.evaluate("isCleared(mine[0].m)"))
    pg.click("#bNext"); pg.wait_for_timeout(300)
    pg.evaluate("ed.objs[0].x += 10; edChanged()")
    check("builder: any edit needs a new clear", pg.evaluate("!isCleared(ed)"))
    pg.evaluate("ed.objs[0].x -= 10; edChanged()")
    rt = pg.evaluate("(() => { const m = decodeLevel(encodeLevel(mine[0].m)); return !!m && contentHash(m) === contentHash(mine[0].m) && isCleared(m); })()")
    check("builder: code round trip keeps the clear", rt)
    check("builder: uncleared codes refused", pg.evaluate("playCustom({ arena: 'M', nameSeed: 1, start: [0, -200], clearT: 0, objs: [] }, 'build') === false"))
    check("builder: custom wins never touch stars", pg.evaluate("Object.keys(progress).every(n => !n.startsWith('✎'))"))
    pg.close()

    # ---- online levels on the pretend server ----
    pg = fresh(ctx, query="?online=mock")
    pg.evaluate("""(() => { const code = encodeLevel({ arena: 'M', nameSeed: 7, start: [0, -200], clearT: 2, objs: [{ t: 'goal', x: 0, y: 280, w: 200, h: 20, a: 0, mo: 0 }] });
      localStorage.setItem('ws_mock_levels', JSON.stringify({ aaa: { code, nameSeed: 7, maker: 'x', created: Date.now(), clearT: 2, pieces: 1, plays: 9, clears: 3, likes: 2, reports: 0 },
        bad: { code, nameSeed: 8, maker: 'y', created: Date.now(), clearT: 2, pieces: 1, plays: 1, clears: 0, likes: 0, reports: 3 } })); })()""")
    pg.click("#bHomeOnline"); pg.wait_for_timeout(400)
    check("online: list from Home, reported level hidden", pg.evaluate("document.querySelectorAll('#onList .lvcard').length") == 1)
    pg.evaluate("playOnline(decodeLevel(JSON.parse(localStorage.getItem('ws_mock_levels')).aaa.code), 'aaa')"); pg.wait_for_timeout(200)
    pg.evaluate("hide('card'); launch()"); pg.wait_for_timeout(200)
    pg.evaluate("timer = 1;" + WIN_AT_GOAL); pg.wait_for_timeout(1500)
    pg.click(".likebtn"); pg.wait_for_timeout(100)
    d = pg.evaluate("JSON.parse(localStorage.getItem('ws_mock_levels')).aaa")
    check("online: plays / clears / likes counted once", (d["plays"], d["clears"], d["likes"]) == (10, 4, 3), (d["plays"], d["clears"], d["likes"]))
    pg.close()
    pg = fresh(ctx)
    pg.click("#bHomeOnline"); pg.wait_for_timeout(4000)  # real Firebase (read-only: just the list)
    t = pg.inner_text("#onList")
    check("online: real Firebase list loads", "Loading" not in t and "Can't reach" not in t and pg.locator("#onTabs button").count() == 4, t[:60])
    pg.close()

    # ---- shop + skins ----
    pg = fresh(ctx, econ={"wallet": 1000})
    pg.click("#bShop"); pg.wait_for_timeout(200)
    pg.evaluate("openShop('flag')"); pg.locator("#skinGrid button", has_text="Japan").click(); pg.click("#bConfirmYes"); pg.wait_for_timeout(150)
    check("shop: buy + equip a flag", pg.evaluate("econ.skin === 'f_japan' && econ.wallet === 850"))
    check("shop: 110 skins, 53 looks", pg.evaluate("SKINS.length") == 110 and pg.evaluate("Object.keys(THEMES).length") == 53)
    pg.close()

    # ---- sounds: every effect callable ----
    pg = fresh(ctx)
    bad = pg.evaluate("['thud','bounce','splat','snap','portal','splash','spike','fall','pop','rocket','click','drop','gem','win','star','missStar','charge','reveal'].filter(n => typeof Sfx[n] !== 'function')")
    check("sounds: all effects exist", not bad, bad)
    pg.close()

    # ---- daily challenge stays separate ----
    pg = fresh(ctx)
    pg.evaluate("playDaily();" + GO + "timer = 1;" + WIN_AT_GOAL); pg.wait_for_timeout(1500)
    check("daily: own level, never unlocks campaign levels", pg.evaluate("dailyRun && Object.keys(progress).length === 0"))
    pg.close()

    # ---- home layout at several sizes ----
    for w, h in [(320, 568), (390, 844), (768, 1024), (2000, 1027)]:
        c2 = b.new_context(viewport={"width": w, "height": h}, is_mobile=w < 800, has_touch=w < 800)
        pg = fresh(c2)
        m = pg.evaluate("""(() => { const e = document.getElementById('scrHome'), o = document.querySelector('.wslide.on .orb').getBoundingClientRect(), p = document.getElementById('bContinue').getBoundingClientRect(),
          d = document.getElementById('bDaily').getBoundingClientRect(), g = document.getElementById('bGift').getBoundingClientRect();
          return [e.scrollHeight - e.clientHeight, Math.round(o.left + o.width / 2 - (p.left + p.width / 2)), Math.round(g.left - d.right)]; })()""")
        check(f"home {w}x{h}: fits, world centred, gap ≥ 10px", m[0] <= 0 and abs(m[1]) <= 1 and m[2] >= 10, m)
        c2.close()

    # ---- 2-player page over http ----
    c3 = b.new_context(viewport={"width": 1280, "height": 720})
    pg = c3.new_page(); pg.on("pageerror", lambda e: ERRS.append("duo: " + str(e)))
    pg.goto(f"http://localhost:{PORT}/duo.html"); pg.wait_for_timeout(1500)
    pg.click("#go"); pg.wait_for_timeout(2900)
    f1 = [f for f in pg.frames if "seat=1" in f.url][0]
    f1.evaluate(WIN_AT_GOAL); pg.wait_for_timeout(1300)
    f2 = [f for f in pg.frames if "seat=2" in f.url][0]
    check("2-player: P1 scores, P2 sees P1's ghost", "P1 1" in pg.inner_text("#score") and f2.evaluate("!!rival"))
    c3.close()
    ctx.close()


def perf(b):
    """Frame times on a 6x-slowed CPU through the heaviest moments."""
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg = fresh(ctx)
    cdp = ctx.new_cdp_session(pg)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 6})
    meas = """(ms) => new Promise(res => { const t = []; let l = performance.now(); const end = l + ms;
      const f = now => { t.push(now - l); l = now; if (now < end) requestAnimationFrame(f); else { t.sort((a, b) => a - b);
        res({ fps: Math.round(1000 / (t.reduce((a, b) => a + b, 0) / t.length)), p95: Math.round(t[Math.floor(t.length * 0.95)]), lowFx }); } };
      requestAnimationFrame(f); })"""
    for label, setup in [
        ("idle level", "loadLevel(20);" + GO),
        ("gem + fireworks", "loadLevel(1);" + GO + "const g = level.objs.find(o => o.t === 'gem'); ball.x = g.x; ball.y = g.y;"),
        ("landing burst", "loadLevel(3);" + GO + "timer = 0.5;" + WIN_AT_GOAL),
        ("underwater world", "loadLevel(172);" + GO),
        ("chest opening", "hide('win'); openChest({ prize: { skin: SKINS[5], tier: 3 }, gems: 20, world: 3 }); setTimeout(() => document.getElementById('chestWrap').click(), 300)"),
    ]:
        pg.evaluate(setup)
        r = pg.evaluate(meas, 2500)
        print(f"PERF {label:<18} {r['fps']:>3} fps  95th pct frame {r['p95']:>3} ms  lowFx={r['lowFx']}", flush=True)
        pg.evaluate("hide('chest'); hide('win'); fireworks = []; particles = [];")
    ctx.close()


def main():
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--directory", str(ROOT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge")
            suite(b)
            if "--perf" in sys.argv:
                perf(b)
            b.close()
    finally:
        srv.terminate()
    print(f"\n{len(FAILS)} failed, page errors: {ERRS or 'none'}")
    sys.exit(1 if FAILS or ERRS else 0)


if __name__ == "__main__":
    main()

"""Build the CrazyGames upload: index.html + their SDK + Data-module saves, zipped.

The web build (GitHub Pages) stays dependency-free and ad-free. This script makes a copy that
loads the CrazyGames SDK v3 and sets WS_BUILD = "crazygames", so the Platform layer in index.html
switches to CrazyGames ads, gameplayStart/Stop, happytime, their mute setting and "land straight
in gameplay".

Saves: CrazyGames wants progress in their Data module (it follows a player who logs in). The game
itself keeps using localStorage; a small loader in this build runs first: it awaits SDK.init(),
copies each saved key from the Data module into localStorage (or, on a player's first run, the old
local save into the Data module), then mirrors every later write of those keys to the Data module,
and only then starts the game. Playtest stats, ghosts and error logs stay local (size limit 1 MB).
In the submission form, turn on "Progress Save" or the Data module stays off.

    python world-shifter/tools/build_crazygames.py
    -> builds/crazygames/index.html and builds/world-shifter-crazygames.zip (upload the zip)
"""
import pathlib, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "world-shifter" / "index.html"
OUT = ROOT / "builds" / "crazygames"
SDK = '<script>window.WS_BUILD = "crazygames";</script>\n<script src="https://sdk.crazygames.com/crazygames-sdk-v3.js"></script>\n'
SYNC = ["ws_stars", "ws_gems", "ws_econ", "ws_seen", "ws_daily", "ws_mine", "ws_online", "ws_auth", "ws_progress",
        "ws_music", "ws_muted", "ws_eyes", "ws_sens", "ws_vibe"]
LOADER = """<script>
// CrazyGames build: saves live in the SDK's Data module; the game starts once they are in place
(async () => {
  const SYNC = %s;
  try {
    const sdk = window.CrazyGames && window.CrazyGames.SDK;
    if (sdk) {
      await sdk.init(); window.__cgInited = true;
      const d = sdk.data;
      for (const k of SYNC) {
        let v = null; try { v = d.getItem(k); } catch (e) {}
        if (v !== null && v !== undefined) localStorage.setItem(k, v);
        else { const l = localStorage.getItem(k); if (l !== null) { try { d.setItem(k, l); } catch (e) {} } }
      }
      const set = Storage.prototype.setItem, rem = Storage.prototype.removeItem;
      Storage.prototype.setItem = function (k, v) { set.call(this, k, v); if (this === window.localStorage && SYNC.includes(k)) { try { d.setItem(k, String(v)); } catch (e) {} } };
      Storage.prototype.removeItem = function (k) { rem.call(this, k); if (this === window.localStorage && SYNC.includes(k)) { try { d.removeItem(k); } catch (e) {} } };
    }
  } catch (e) { console.warn("CrazyGames Data module unavailable, using local saves", e); }
  const s = document.createElement("script"); s.textContent = document.getElementById("wsgame").textContent; document.body.appendChild(s);
})();
</script>
""" % SYNC


def main():
    html = SRC.read_text(encoding="utf-8")
    assert html.count("<style>") == 1, "expected one <style> in index.html"
    html = html.replace("<style>", SDK + "<style>")  # SDK must load before the game script runs
    game_open = '<script>\n"use strict";'
    assert html.count(game_open) == 1, "expected one main game <script>"
    html = html.replace(game_open, '<script type="text/plain" id="wsgame">\n"use strict";')  # started by the loader
    assert html.count("</body>") == 1
    html = html.replace("</body>", LOADER + "</body>")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8", newline="")
    zpath = OUT.parent / "world-shifter-crazygames.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(OUT / "index.html", "index.html")
    kb = zpath.stat().st_size / 1024
    print(f"built {OUT / 'index.html'}\nzip   {zpath} ({kb:.0f} KB; CrazyGames limit for the initial download is 50 MB, 20 MB for mobile)")


if __name__ == "__main__":
    main()

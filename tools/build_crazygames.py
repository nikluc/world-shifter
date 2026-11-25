"""Build the CrazyGames upload: index.html + their SDK, zipped.

The web build (GitHub Pages) stays dependency-free and ad-free. This script makes a copy that
loads the CrazyGames SDK v3 and sets WS_BUILD = "crazygames", so the Platform layer in index.html
switches to CrazyGames ads, gameplayStart/Stop and "land straight in gameplay".

    python world-shifter/tools/build_crazygames.py
    -> builds/crazygames/index.html and builds/world-shifter-crazygames.zip (upload the zip)
"""
import pathlib, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "world-shifter" / "index.html"
OUT = ROOT / "builds" / "crazygames"
SDK = '<script>window.WS_BUILD = "crazygames";</script>\n<script src="https://sdk.crazygames.com/crazygames-sdk-v3.js"></script>\n'


def main():
    html = SRC.read_text(encoding="utf-8")
    marker = "<style>"
    assert html.count(marker) == 1, "expected one <style> in index.html"
    html = html.replace(marker, SDK + marker)  # SDK must load before the game script runs
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8", newline="")
    zpath = OUT.parent / "world-shifter-crazygames.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(OUT / "index.html", "index.html")
    kb = zpath.stat().st_size / 1024
    print(f"built {OUT / 'index.html'}\nzip   {zpath} ({kb:.0f} KB; CrazyGames limit for the initial download is 50 MB)")


if __name__ == "__main__":
    main()

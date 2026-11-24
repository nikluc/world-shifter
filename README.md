# World Shifter (prototype)

You don't move the ball — you turn the world. Rotate the level so the falling ball lands on the green pad, dodging spikes, spinning blades and the void.

**Play:** https://nikluc.github.io/world-shifter/ (works best on a phone)

- Tap / click / Space to drop the ball
- Drag or draw circles to rotate (keyboard: ← → or A D, Q/E snap 90°, R restart); 90° mode has ⟲ ⟳ buttons
- 60 levels in one run from easiest to hardest, with ★ for speed
- Along the way: portals (linked pairs, keep your speed), ice (no grip) and glue (holds the ball while you turn)
- Sound effects and background music (♫ toggles music, 🔊 mutes all, incl. vibration)
- Dotted landing preview on the first 5 levels, and on any level after 20 deaths there; a ghost replays your best run

**Playtesters:** tap the version text in the menu 5 times (or open `?stats`) to see your stats, then press **Copy** (or **Save file**) and send it over. It includes where you died and your best route on each level.

`tools/level_bot.py` checks every level is winnable *by a human* (wins must survive sloppy timing), scores difficulty, and with `--paths sheet.png` draws each level's winning route to spot shortcuts (needs Playwright + Edge + Pillow).

This is an early prototype for playtesting — feedback welcome.

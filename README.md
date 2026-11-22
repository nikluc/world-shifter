# World Shifter (prototype)

You don't move the ball — you turn the world. Rotate the level so the falling ball lands on the green pad, dodging spikes, spinning blades and the void.

**Play:** https://nikluc.github.io/world-shifter/ (works best on a phone)

- Tap / click / Space to drop the ball
- Drag or draw circles to rotate (keyboard: ← → or A D, Q/E snap 90°, R restart)
- 60 levels in one run from easiest to hardest, with ★ for speed
- Along the way: portals (linked pairs, keep your speed), ice (no grip) and glue (holds the ball while you turn)
- Sound effects and background music (♫ toggles music, 🔊 mutes all, incl. vibration)
- Dotted landing preview on the first 5 levels; a ghost replays your best run

**Playtesters:** tap the version text in the menu 5 times (or open `?stats`) to see your stats, then press **Copy** and send them over.

`tools/level_bot.py` checks every level is winnable and measures its difficulty (needs Playwright + Edge).

This is an early prototype for playtesting — feedback welcome.

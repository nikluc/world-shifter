# World Shifter (prototype)

You don't move the ball — you turn the world. Rotate the level so the falling ball lands on the green pad, dodging spikes, spinning blades and the void.

**Play:** https://nikluc.github.io/world-shifter/ (works best on a phone)

- Tap, click, Space, or turning the world in any way drops the ball
- Drag or draw circles to rotate (keyboard: ← → or A D, Q/E snap 90°, R restart); 90° mode has ⟲ ⟳ buttons
- 500 levels in one run from easiest to hardest, with ★ for speed: 60 hand-made, 440 generated and bot-checked
- A hidden ◆ gem on 469 of 500 levels (each proven collectable by the bot), and a Share button that sends your result with a link to that level
- Along the way: portals (linked pairs, keep your speed), ice (no grip) and glue (holds the ball while you turn)
- Sound effects and 6 synthesized songs (a new one every 50 levels) whose arrangement and melody keep evolving
- ⚙ settings: music, sound, vibration, and controls (drag/circle or 90° buttons); the game pauses when you switch apps
- 10 worlds of 50 levels, each with its own colours and song; a 📅 daily challenge level (same for everyone) with its own share text; an ending after level 500
- First-time help: an animated circle gesture on level 1, and a short card the first time each new piece appears
- Dotted landing preview on the first 5 levels, and on any level after 20 deaths there; a ghost replays your best run

**Playtesters:** tap the version text in the menu 5 times (or open `?stats`) to see your stats, then press **Copy** (or **Save file**) and send it over. It includes where you died and your best route on each level.

This web version has no ads. The same `index.html` also builds for CrazyGames (`tools/build_crazygames.py`) and Android/iOS through a Platform layer that switches ads, analytics and crash reporting per platform.

`tools/gen_levels.py` grows the run (search seeds, keep only levels a human can win that no single tilt solves, then build the ordered run); `tools/place_gems.py` places gems the bot can prove are collectable. `tools/level_bot.py` checks every level is winnable *by a human* (wins must survive sloppy timing), scores difficulty, and with `--paths sheet.png` draws each level's winning route to spot shortcuts (needs Playwright + Edge + Pillow).

This is an early prototype for playtesting — feedback welcome.

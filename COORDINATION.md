# Kingdoms AI — Parallel Work Coordination

Paste this into whichever Claude session you're using (yours or your
friend's) before starting work. It tells Claude the current true state of
the repo, who's touching what, and how to avoid stepping on the other
person's changes. Update the "Current status" and "Active work" sections
whenever something changes hands.

---

## Why this file exists

Two people are working on the same repo through two separate Claude
conversations that don't know about each other. Neither Claude can see what
the other one did. Without this file, one session will build on stale
assumptions and either duplicate work or silently break something the other
person just fixed -- exactly what almost happened here: a merge dropped a
completed province-combat rewrite for a few minutes before it got caught.

## Current status (as of this merge)

Everything below is confirmed working, tested end-to-end with
`tests/mock_playthrough.py --turns 7`:

- Full economy: tax income, upkeep, food, population growth/starvation
- Tech tree with real prereq chains: industrial -> rocketry -> space chain,
  plus aircraft carrier -> aerial fortress (helicarrier-class), plus
  petrochemical refining
- Tax-driven unrest: sustained high tax erodes stability, riots fire
  automatically (population/treasury/military losses), repairable by
  spending money
- Custom/fictional inventions: kingdoms propose their own named project with
  a self-set cost; engine validates affordability, power_rating is always
  computed mechanically from cost (never trusts the AI's claims about what
  it does)
- **Province-level adjacency and combat** (built by the other contributor):
  `data/map.json` has real `borders` lists per province/island;
  `src/map.py` has `provinces_adjacent()`, `province_borders()`,
  `province_owner()`, `is_island()`; `move_units` only works one hop along
  real borders; moving into enemy territory while at war IS the attack;
  combat resolves locally from whatever units are actually standing in that
  specific province, not kingdom-wide totals; moving onto an unclaimed
  island claims it
- God-view HTML map: real map image embedded as base64 (self-contained,
  works from any folder), clickable region hotspots, animated SVG icons for
  every unit type + infrastructure (no emoji anywhere -- some Windows font
  builds are missing glyphs and render tofu boxes), forces-abroad panel
  showing invading/staged/claimed troops outside home territory, island
  ownership coloring, persistent bottom panel for conference + all secret
  meetings
- `openrouter/free` auto-router used for all five kingdoms by default so the
  game runs with zero setup; fast-fail + auto-fallback logic in
  `llm_agent.py` so a stale model slug can't crash the game or hang for
  minutes retrying something that will never succeed
- Auto-opens `maps/latest.html` in your browser when a run finishes
  (`main.py` and `tests/mock_playthrough.py` both do this)

## Known open items (pick one, don't do all of them in the same session)

1. **`player_llm` is still on `openrouter/free`**, not actually your own
   model. Swap to `"ollama/llama3.1"` (after installing Ollama, see
   README) or a real hosted endpoint once decided.
2. **No formal alliance/treaty mechanic.** `alliances` exists as a field but
   nothing in `orchestrator.py` lets kingdoms actually form or honor one --
   diplomacy currently only produces conference chat + secret meeting
   transcripts, not binding effects.
3. **Conquered territory doesn't change continent ownership.** Winning a
   battle on foreign soil currently only causes casualties -- `province_owner()`
   is still fixed to whichever kingdom's continent it started on. Capturing
   a province (updating ownership permanently) isn't implemented.
4. **Static HTML only.** The map regenerates fresh each turn but doesn't
   live-update -- you have to re-run and refresh. A live web view (Flask/
   FastAPI + auto-refresh, or a native app window via `pywebview`) is a real
   upgrade, not yet started.
5. **Model slugs for the four AI kingdoms are generic** (`openrouter/free`
   for all of them right now, for reliability). If you want distinct named
   models back for flavor, pick current live slugs from
   `openrouter.ai/models?max_price=0` -- the fallback logic means a stale
   pick won't crash things anymore, just silently reroute.

## How to avoid conflicting work

- **Before starting, both people should re-export/re-share the current repo
  state** (zip or a fresh GitHub pull) so both Claude sessions are working
  from the same baseline -- this file describes intent, not a live diff.
- **Pick different files/systems per session.** The riskiest overlap so far
  was two sessions both touching `orchestrator.py` and `map_render.py`
  around the same time. If you're both actively coding, split by system:
  e.g. one person owns `src/orchestrator.py` + `src/map.py` (game logic),
  the other owns `src/map_render.py` (visuals) -- they touch different files
  most of the time.
- **Whoever finishes a change should re-run `tests/mock_playthrough.py`
  before handing the repo back**, and briefly note in this file's "Current
  status" section what changed. A change that isn't tested and isn't
  mentioned here is invisible to the other session.
- **When merging two sets of changes, diff every file, don't just overwrite.**
  `diff -q old_dir/file new_dir/file` first; if both differ from a shared
  baseline, read both diffs before picking one wholesale -- this is exactly
  how the province-combat rewrite almost got silently dropped during the
  last merge.

## Conventions (unchanged, still apply)

- Money in raw dollars, never abbreviated.
- Every new `Kingdom`/`GameState` field needs a sensible default.
- Any file write must use `encoding="utf-8"` explicitly (Windows defaults to
  cp1252 and will crash on non-ASCII otherwise).
- No emoji in generated HTML/console output -- plain text or CSS/SVG only.
- The engine is the source of truth. Any AI-proposed action with a cost gets
  validated in `orchestrator.py` before being applied -- never trust the
  model's own arithmetic or claims about what something does.

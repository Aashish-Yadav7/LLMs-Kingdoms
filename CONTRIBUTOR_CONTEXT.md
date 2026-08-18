# Kingdoms AI — Collaborator Context

Paste this whole file into a new Claude conversation before asking for help.
It gives Claude everything it needs to work on this repo as a collaborator
without you having to re-explain the project from scratch.

---

## What this project is

A turn-based strategy game where 4-5 kingdoms are each played by a different
LLM (Claude, Gemini, GPT, Grok, plus one reserved for a custom/self-hosted
model). The owner (Aashish) is a spectator/god who watches all of them build
economies, research tech, negotiate, and fight -- entirely autonomously, no
manual play. The game engine (economy, tech tree, combat, resources) is
deterministic Python code the AIs cannot bend; they only ever choose actions
within rules the engine enforces.

## Repo layout

```
kingdoms-ai/
├── main.py                   # real entrypoint (needs API keys)
├── tests/mock_playthrough.py # runs the full engine with FAKE agents, no API keys needed -- use this to test
├── requirements.txt
├── .env.example               # copy to .env, add OPENROUTER_API_KEY
├── data/
│   ├── map.json                # continents, provinces, terrain, ownership
│   ├── world_map.png            # the actual map image (background for the god-view HTML)
│   └── save_*.json              # autosaves per turn (gitignored)
├── logs/                       # readable turn-by-turn transcripts (gitignored)
├── maps/                       # generated HTML god-view, latest.html always overwritten (gitignored)
└── src/
    ├── config.py                # kingdom -> model mapping, personalities, constants
    ├── state.py                  # Kingdom / GameState dataclasses, save/load, intel_view()
    ├── map.py                     # loads data/map.json, generates resource deposits
    ├── grid.py                     # 2D coordinate grid (foundation for future movement/pathfinding)
    ├── tech_tree.py                 # research tree: costs, prereqs, unlocks
    ├── military.py                   # unit types, costs, combat resolution
    ├── economy.py                     # tax, upkeep, food, stability/unrest, research progress
    ├── diplomacy.py                     # public conference + consent-based secret 1:1 meetings
    ├── orchestrator.py                   # THE MAIN TURN LOOP -- ties everything together
    ├── map_render.py                      # generates the clickable HTML god-view
    └── agents/
        ├── base_agent.py                   # abstract interface
        └── llm_agent.py                      # OpenRouter-backed agent, works for any model string
```

## Core design principles (don't break these)

1. **The engine is the source of truth, never the AI.** Every costed action
   (build unit, start research, declare war) gets validated against treasury/
   tech/prereqs in `orchestrator.py` before being applied. An LLM proposing
   something illegal or unaffordable gets partially filled or rejected, never
   trusted blindly.
2. **Asymmetric intel.** `Kingdom.intel_view(viewer_id)` in `state.py` is how
   one kingdom's data is shown to another. Normal kingdoms only ever see
   `public_summary()` of others (noisy approximate numbers). `player_llm`
   (the user's own model, south pole) sees exact numbers on everyone --
   that's an intentional advantage and must never leak into another
   kingdom's prompt in `orchestrator.py`.
3. **God view shows everything, always exact.** `map_render.py` always uses
   real numbers for every kingdom (never the noisy public view) since the
   human spectator should see the truth regardless of what the AIs know
   about each other.
4. **One agent class for every model.** `LLMAgent` in `llm_agent.py` talks to
   any model through OpenRouter's OpenAI-compatible endpoint. Don't write
   provider-specific agent classes -- just change the `model` string in
   `config.py`.

## Current state / what's implemented

- Full economy tick (tax income, upkeep, food, population growth/starvation)
- Tech tree with real prerequisite chains, including a space chain
  (satellite -> orbital rocketry -> space program -> deep space) and an
  advanced military chain (aircraft carriers -> aerial fortress/helicarrier-class)
- Tax-driven unrest: tax rate above 30% builds instability over time; if
  stability collapses, a riot fires automatically (population loss, treasury
  damage, military losses). Kingdoms can spend money to actively repair
  stability (`apply_repair_investment` in `economy.py`).
- Unit positions per-province (`Kingdom.unit_positions`) plus a `move_units`
  action, laying groundwork for spatial combat (not yet wired into combat
  resolution, which still uses aggregate totals).
- Public conference + consent-based secret 1:1 diplomacy each turn.
- HTML god-view map: real map image embedded as base64 (so it's a
  self-contained file, works regardless of how you open/serve it), clickable
  region hotspots opening a stats panel, persistent bottom panel showing
  conference + all secret meetings.
- `player_llm` kingdom gets a tech head start, 1.5x research speed, and full
  intel on everyone -- reflecting a Napoleon/Alexander-style strategic edge,
  never revealed to the other four kingdoms.

## What's mid-flight / not finished yet

- **Custom/fictional inventions**: kingdoms should be able to propose their
  own named projects (not just picking from the fixed tech tree) with a
  self-proposed cost/turns, validated by the engine for affordability. Fields
  exist on `Kingdom` (`custom_researching`, `custom_projects`) but the
  orchestrator doesn't yet process a `custom_project` action from the LLM
  decision schema, and `map_render.py` doesn't display them yet.
- **A real bug just found and partially fixed**: tech research was never
  actually deducting its `cost` from treasury -- only turns were tracked.
  Fix in progress in `orchestrator.py`'s research-start logic.
- **Combat still uses aggregate `units`, not `unit_positions`** -- no
  front-line/province-based combat yet, just kingdom-vs-kingdom totals.
- Your own hosted model isn't wired in yet (`config.py` has
  `"model": "custom/your-model-id"` as a placeholder) -- needs a real
  base_url/api_key once decided.

## How to test without spending any API budget

```bash
python tests/mock_playthrough.py --turns 10
```
Runs the whole engine with a scripted fake agent instead of real LLM calls.
Then open `maps/latest.html` directly in a browser (double-click works fine,
the map image is embedded, no server needed).

## Conventions to follow

- Money is always in raw dollars (e.g. `100_000_000_000_000` for $100T), not
  abbreviated -- keeps all economy math exact.
- Every dataclass field on `Kingdom`/`GameState` needs a sensible default so
  `GameState.new_game()` and `GameState.load()` both keep working.
- Any new file write must use `encoding="utf-8"` explicitly -- Windows
  defaults to cp1252 and will crash on emoji/unicode otherwise (this bit us
  once already).
- No emoji in generated HTML/console output for the same reason -- use plain
  text labels or CSS-based badges instead.

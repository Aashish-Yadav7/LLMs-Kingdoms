# Kingdoms AI
kkkkk
Four (or more) kingdoms, each run by a different LLM, competing over a shared
economy/military/tech simulation. The game engine (economy, tech tree, combat,
resource limits) is deterministic Python code — the AIs only ever choose
*actions* within rules they can't bend. This keeps things "real world": no
kingdom can build a tank without steel, fuel, and money, no matter what the
model says.

## How it works

Each turn:

1. **Economy tick** — engine applies tax income, population upkeep (food/money),
   resource production, and maintenance costs automatically.
2. **Private planning** — each kingdom's LLM sees only its own state + public
   info about others, and privately decides what to do this turn.
3. **Conference (public)** — all kingdoms exchange one round of public
   messages, visible to everyone.
4. **Secret meetings (optional)** — any kingdom can request a 1:1 private
   channel with another kingdom. Only those two see it.
5. **Action resolution** — engine validates and applies every kingdom's
   submitted action (build unit, research tech, propose alliance, attack,
   trade, etc.), enforcing costs/prereqs. Illegal or unaffordable actions are
   rejected, not silently allowed.
6. State is saved to `data/save_<n>.json` and a human-readable log is written
   to `logs/`.

## Project layout

```
kingdoms-ai/
├── main.py                  # entrypoint, run this
├── requirements.txt
├── .env.example              # copy to .env and fill in API keys
├── data/
│   ├── initial_state.json    # starting kingdoms, treasury, map regions
│   └── save_*.json           # autosaves per turn
├── logs/                     # readable turn-by-turn transcripts
└── src/
    ├── config.py              # kingdom -> model mapping, engine constants
    ├── state.py                # Kingdom / GameState data classes + save/load
    ├── tech_tree.py             # research tree: costs, prereqs, unlocks
    ├── military.py              # unit types, costs, combat resolution
    ├── economy.py               # tax, upkeep, production, resource math
    ├── diplomacy.py              # conference + secret meeting plumbing
    ├── orchestrator.py           # the main turn loop
    └── agents/
        ├── base_agent.py         # abstract agent interface
        └── llm_agent.py           # OpenRouter-backed agent (any model)
```

## Setup

```bash
cd kingdoms-ai
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and add OPENROUTER_API_KEY=sk-or-...
```

Get a free OpenRouter key at https://openrouter.ai/keys — no card required for
`:free`-tagged models. Free tier is rate-limited (roughly tens of requests/day
per model, more once you add a small credit balance), which is fine for a
turn-based game where each kingdom acts a handful of times per turn.

## Setting up your own LLM (player_llm / south pole kingdom) via Ollama

Ollama runs models entirely on your own machine -- free, no API key, no rate
limits, but needs enough RAM/GPU for whatever model you pick.

1. Install Ollama: https://ollama.com/download (Windows/Mac/Linux all supported)
2. Pull a model, e.g.:
   ```bash
   ollama pull llama3.1
   ```
3. Ollama runs a local server automatically after install (default
   `http://localhost:11434`). Nothing else to configure -- `config.py`
   already points `player_llm` at `"ollama/llama3.1"`.
4. Swap `llama3.1` for any model Ollama supports (`ollama pull mistral`,
   `ollama pull qwen2.5`, etc.) by changing the model string in
   `src/config.py` to match.

If your machine can't run a good local model well, swap `player_llm`'s model
in `config.py` to `"groq/llama-3.3-70b-versatile"` instead (free tier, runs
on Groq's servers, much faster than most local setups) -- get a free key at
https://console.groq.com/keys and put it in `.env` as `GROQ_API_KEY`.

## Assigning models to kingdoms

Edit `src/config.py`:

```python
KINGDOMS = {
    "north": {"name": "Kingdom of the North", "model": "deepseek/deepseek-v4:free"},
    "east":  {"name": "Eastern Dominion",       "model": "moonshotai/kimi-k2.6:free"},
    "south": {"name": "Southern Republic",       "model": "qwen/qwen3.6:free"},
    "west":  {"name": "Western Alliance",        "model": "z-ai/glm-5.1:free"},
}
```

Any OpenRouter model string works here — including your own fine-tuned model
if you host it behind an OpenAI-compatible endpoint (set `OPENROUTER_BASE_URL`
in `.env` to point at it instead). Swapping a kingdom to Claude, GPT, Gemini,
or Grok later is just changing the model string and API key/base URL — the
rest of the engine doesn't care who's playing.

## Running

```bash
python main.py --turns 5
```

Each turn's output prints to console and gets logged to `logs/turn_N.md` so
you can read the diplomacy transcripts afterward.

## The map

You mentioned you already have a map. Drop it as `data/map.json` (or a plain
image reference) with regions/provinces, and I'll wire `state.py` and
`military.py` to use real region adjacency for movement/attacks instead of an
abstract "kingdom vs kingdom" model. Tell me its format (list of regions +
borders? image + coordinates?) and I'll adapt the loader.

"""
Central config: which model runs which kingdom, and global engine constants.
Change KINGDOMS to swap models in/out. Every model is called through the same
OpenAI-compatible interface (OpenRouter), so swapping is just a string change.
"""

import os
from dotenv import load_dotenv

# Loaded here (not just in main.py) so these env lookups work no matter which
# module gets imported first -- config.py is pulled in very early via
# src/state.py, before main.py's own load_dotenv() call would otherwise run.
load_dotenv()

STARTING_TREASURY = 100_000_000_000_000  # $100 trillion
STARTING_POPULATION = 50_000_000
STARTING_FOOD_STORAGE = 5_000_000_000  # tons, arbitrary unit

# Every kingdom's model is driven by a .env variable, with a safe Ollama
# default if you haven't set one. This means swapping providers -- to test
# a paid one, a different free one, whatever -- is just editing .env, never
# touching this file. No real provider name is hardcoded as the only option
# anywhere below; whatever you put in .env wins.
#
# Format for each variable: "<provider_prefix>/<model_name>", e.g.
#   ollama/llama3.2        (free, local, default)
#   cerebras/gpt-oss-120b  (free tier, but has hit payment walls before)
#   nvidia/meta/llama-3.1-70b-instruct   (free tier)
#   groq/llama-3.3-70b-versatile        (free tier)
#   xai/grok-4.3           (NOT FREE -- real per-token billing, use deliberately)
#   openrouter/free        (OpenRouter's auto-router)
#   custom/your-model-id   (your own hosted endpoint)
DEFAULT_MODEL = "ollama/llama3.2"

NORTH_MODEL = os.environ.get("NORTH_MODEL", DEFAULT_MODEL)
EAST_MODEL = os.environ.get("EAST_MODEL", DEFAULT_MODEL)
SOUTH_MODEL = os.environ.get("SOUTH_MODEL", DEFAULT_MODEL)
WEST_MODEL = os.environ.get("WEST_MODEL", DEFAULT_MODEL)
PLAYER_LLM_MODEL = os.environ.get("PLAYER_LLM_MODEL", DEFAULT_MODEL)

KINGDOMS = {
    "north": {
        "name": "Kingdom of the North",
        "model": NORTH_MODEL,
        "personality": (
            "Pragmatic industrial strategist. Favors steady economic growth, "
            "efficient infrastructure, and calculated military buildup over risk-taking."
        ),
    },
    "east": {
        "name": "Eastern Dominion",
        "model": EAST_MODEL,
        "personality": (
            "Opportunistic and adaptive. Watches other kingdoms closely, quick to "
            "propose or break alliances when it sees advantage."
        ),
    },
    "south": {
        "name": "Southern Republic",
        "model": SOUTH_MODEL,
        "personality": (
            "Diplomacy-first. Prefers trade deals, research cooperation, and "
            "coalition-building over unilateral military spending."
        ),
    },
    "west": {
        "name": "Western Alliance",
        "model": WEST_MODEL,
        "personality": (
            "Defensive and cautious. Prioritizes food security, population "
            "welfare, and fortification; slow to commit to offensive wars."
        ),
    },
    # South pole kingdom -- reserved for YOUR own LLM. Same "llama3.2" as the
    # others for now, purely for a reliable first run. Once everything's
    # confirmed working, this is the one to make distinct: pull a bigger
    # model if your machine can handle it (`ollama pull llama3.1` or
    # `ollama pull qwen2.5:14b`) and swap the string below, or point it at a
    # different Ollama model than the other four so it doesn't think exactly
    # like them. This kingdom gets real strategic advantages defined below
    # (intel, research speed, tech head start) -- none of which are ever
    # mentioned to the other four kingdoms' prompts.
    "player_llm": {
        "name": "The Frozen Reach",
        "model": PLAYER_LLM_MODEL,
        "personality": (
            "An empire-builder in the mold of Napoleon and Alexander: relentlessly "
            "expansionist, decisive, and opportunistic, but always in service of a "
            "long-range strategic vision rather than impulsive aggression. Prioritizes "
            "outpacing every rival technologically, Space race, build helicarriers, advanced missiles, -- pursues and funds every available "
            "invention, especially frontier tech (rocketry, space) -- while building "
            "the economic and military base to project power outward. Sees the empire's "
            "growth as inevitable, not optional: consolidate, industrialize, then expand, "
            "and never stop building toward the next frontier."
        ),
    },
}

# Strategic edge granted only to player_llm -- never revealed to the other
# four kingdoms' prompts or logs shown to them.
PLAYER_LLM_RESEARCH_SPEED_MULTIPLIER = 1.5  # 50% faster research progress per turn
PLAYER_LLM_STARTING_TECH = {"basic_industry", "combustion_engines", "basic_rocketry"}  # head start

# Maps each kingdom id to its continent id in data/map.json. Must match the
# "owner" field set on each continent in that file.
KINGDOM_CONTINENTS = {
    "north": "north",
    "east": "east",
    "south": "south",
    "west": "west",
    "player_llm": "south_pole",
}

MAP_RNG_SEED = 42  # change this for a different randomized resource layout each new game

# Turn structure timing (in-game, not real time)
PHASES = ["economy_tick", "private_planning", "conference", "secret_meetings", "resolution"]

# Diplomacy limits (to stop context/token blowup, not a "real" game rule)
MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN = 5
MAX_SECRET_MEETINGS_PER_TURN = 5
"""
Central config: which model runs which kingdom, and global engine constants.
Change KINGDOMS to swap models in/out. Every model is called through the same
OpenAI-compatible interface (OpenRouter), so swapping is just a string change.
"""

STARTING_TREASURY = 100_000_000_000_000  # $100 trillion
STARTING_POPULATION = 50_000_000
STARTING_FOOD_STORAGE = 5_000_000_000  # tons, arbitrary unit

# OpenRouter's free-model catalog rotates constantly -- specific model slugs
# (deepseek-v4, kimi-k2.6, etc.) get renamed or retired without warning. Using
# "openrouter/free" (OpenRouter's own auto-router) always resolves to
# WHATEVER free model is currently live, so it can never 404 on a stale name.
# If you want a specific named model instead, copy its exact slug from
# https://openrouter.ai/models?max_price=0 (reflects what's actually live
# right now) -- llm_agent.py will automatically fall back to "openrouter/free"
# if that specific slug ever 404s, so a stale name won't crash the game.
KINGDOMS = {
    "north": {
        "name": "Kingdom of the North",
        "model": "cerebras/gpt-oss-120b",
        "personality": (
            "Pragmatic industrial strategist. Favors steady economic growth, "
            "efficient infrastructure, and calculated military buildup over risk-taking."
        ),
    },
    "east": {
        "name": "Eastern Dominion",
        "model": "cerebras/gpt-oss-120b",
        "personality": (
            "Opportunistic and adaptive. Watches other kingdoms closely, quick to "
            "propose or break alliances when it sees advantage."
        ),
    },
    "south": {
        "name": "Southern Republic",
        "model": "cerebras/gpt-oss-120b",
        "personality": (
            "Diplomacy-first. Prefers trade deals, research cooperation, and "
            "coalition-building over unilateral military spending."
        ),
    },
    "west": {
        "name": "Western Alliance",
        "model": "cerebras/gpt-oss-120b",
        "personality": (
            "Defensive and cautious. Prioritizes food security, population "
            "welfare, and fortification; slow to commit to offensive wars."
        ),
    },
    # South pole kingdom -- reserved for YOUR own LLM. Set to NVIDIA Build
    # (NIM) since that's the key you have -- free, hosts 100+ open models.
    # "meta/llama-3.1-70b-instruct" below is a solid stable default; swap to
    # any model listed at https://build.nvidia.com/models (format is
    # "nvidia/<provider>/<model-name>" -- note the double slash, that's
    # correct, NVIDIA's own model names contain a slash too). This kingdom
    # gets real strategic advantages defined below (intel, research speed,
    # tech head start) -- none of which are ever mentioned to the other
    # four kingdoms' prompts.
    "player_llm": {
        "name": "The Frozen Reach",
        "model": "nvidia/meta/llama-3.1-70b-instruct",
        "personality": (
            "An empire-builder in the mold of Napoleon and Alexander: relentlessly "
            "expansionist, decisive, and opportunistic, but always in service of a "
            "long-range strategic vision rather than impulsive aggression. Prioritizes "
            "outpacing every rival technologically -- pursues and funds every available "
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
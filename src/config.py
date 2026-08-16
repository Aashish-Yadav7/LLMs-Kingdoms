"""
Central config: which model runs which kingdom, and global engine constants.
Change KINGDOMS to swap models in/out. Every model is called through the same
OpenAI-compatible interface (OpenRouter), so swapping is just a string change.
"""

STARTING_TREASURY = 100_000_000_000_000  # $100 trillion
STARTING_POPULATION = 50_000_000
STARTING_FOOD_STORAGE = 5_000_000_000  # tons, arbitrary unit

# Free/cheap OpenRouter models as of mid-2026. Availability and exact ids on
# OpenRouter rotate -- check https://openrouter.ai/models?order=pricing-low
# and swap the string here if one goes stale. ":free" suffix = zero cost tier.
KINGDOMS = {
    "north": {
        "name": "Kingdom of the North",
        "model": "deepseek/deepseek-v4:free",
        "personality": (
            "Pragmatic industrial strategist. Favors steady economic growth, "
            "efficient infrastructure, and calculated military buildup over risk-taking."
        ),
    },
    "east": {
        "name": "Eastern Dominion",
        "model": "moonshotai/kimi-k2.6:free",
        "personality": (
            "Opportunistic and adaptive. Watches other kingdoms closely, quick to "
            "propose or break alliances when it sees advantage."
        ),
    },
    "south": {
        "name": "Southern Republic",
        "model": "qwen/qwen3.6:free",
        "personality": (
            "Diplomacy-first. Prefers trade deals, research cooperation, and "
            "coalition-building over unilateral military spending."
        ),
    },
    "west": {
        "name": "Western Alliance",
        "model": "z-ai/glm-5.1:free",
        "personality": (
            "Defensive and cautious. Prioritizes food security, population "
            "welfare, and fortification; slow to commit to offensive wars."
        ),
    },
    # South pole kingdom -- reserved for YOUR own LLM. Point this at your
    # hosted model via CUSTOM_MODEL_BASE_URL / CUSTOM_MODEL_API_KEY in .env,
    # or swap the model string to any OpenRouter id if you want to test with
    # a stand-in before your own model is ready. This kingdom starts on the
    # richest territory on the map (every resource, high density) and gets
    # real strategic advantages defined below (intel, research speed, tech
    # head start) -- none of which are ever mentioned to the other four
    # kingdoms' prompts.
    "player_llm": {
        "name": "The Frozen Reach",
        "model": "custom/your-model-id",
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
MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN = 2
MAX_SECRET_MEETINGS_PER_TURN = 3

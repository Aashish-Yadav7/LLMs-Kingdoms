"""
Tech tree. Every kingdom starts with nothing unlocked beyond "basic_industry".
Costs are in dollars, research_turns is how many full turns of funded research
it takes. A tech must have all prerequisites unlocked before it can be started.

This is intentionally coarse (not a real 2026 tech tree with hundreds of
nodes) but every tier reflects a real, sequenced dependency: you cannot
research guided missiles before basic rocketry, you cannot build a tank
before combustion engines and armor plating, etc.
"""

TECH_TREE = {
    "basic_industry": {
        "cost": 0, "research_turns": 0, "prereqs": [],
        "unlocks": ["can build: farms, roads, basic factories"],
    },
    "combustion_engines": {
        "cost": 50_000_000_000, "research_turns": 2, "prereqs": ["basic_industry"],
        "unlocks": ["can build: trucks, basic artillery"],
    },
    "armor_plating": {
        "cost": 80_000_000_000, "research_turns": 2, "prereqs": ["combustion_engines"],
        "unlocks": ["can build: armored_vehicle"],
    },
    "basic_rocketry": {
        "cost": 150_000_000_000, "research_turns": 3, "prereqs": ["combustion_engines"],
        "unlocks": ["can build: rocket_artillery"],
    },
    "jet_propulsion": {
        "cost": 300_000_000_000, "research_turns": 3, "prereqs": ["basic_rocketry"],
        "unlocks": ["can build: fighter_jet"],
    },
    "guided_systems": {
        "cost": 500_000_000_000, "research_turns": 4, "prereqs": ["basic_rocketry"],
        "unlocks": ["can build: guided_missile"],
    },
    "advanced_materials": {
        "cost": 400_000_000_000, "research_turns": 3, "prereqs": ["armor_plating"],
        "unlocks": ["can build: main_battle_tank"],
    },
    "naval_engineering": {
        "cost": 350_000_000_000, "research_turns": 3, "prereqs": ["combustion_engines"],
        "unlocks": ["can build: destroyer"],
    },
    "nuclear_physics": {
        "cost": 2_000_000_000_000, "research_turns": 8, "prereqs": ["guided_systems", "advanced_materials"],
        "unlocks": ["can build: nuclear_power_plant (NOT weapons -- see note)"],
    },
    "agri_automation": {
        "cost": 100_000_000_000, "research_turns": 2, "prereqs": ["basic_industry"],
        "unlocks": ["+30% food production"],
    },
    "renewable_grid": {
        "cost": 200_000_000_000, "research_turns": 3, "prereqs": ["basic_industry"],
        "unlocks": ["-20% energy upkeep costs"],
    },
    "cyber_infrastructure": {
        "cost": 250_000_000_000, "research_turns": 3, "prereqs": ["basic_industry"],
        "unlocks": ["intel bonus: see partial info on other kingdoms' public builds"],
    },

    # --- Space chain ---
    "satellite_tech": {
        "cost": 800_000_000_000, "research_turns": 5, "prereqs": ["guided_systems", "cyber_infrastructure"],
        "unlocks": ["can build: recon_satellite -- passive intel on other kingdoms' public activity"],
    },
    "orbital_rocketry": {
        "cost": 1_500_000_000_000, "research_turns": 6, "prereqs": ["satellite_tech", "nuclear_physics"],
        "unlocks": ["can build: launch_vehicle -- required for any orbital payload"],
    },
    "space_program": {
        "cost": 3_000_000_000_000, "research_turns": 8, "prereqs": ["orbital_rocketry"],
        "unlocks": ["can build: space_station -- major prestige + research speed bonus"],
    },
    "deep_space_engineering": {
        "cost": 6_000_000_000_000, "research_turns": 10, "prereqs": ["space_program"],
        "unlocks": ["can build: deep_space_vessel -- endgame tech, no direct combat use"],
    },
}

# NOTE: nuclear weapons are deliberately absent from this tree. If you want a
# WMD tier for narrative tension, model it as a diplomatic/economic "doomsday"
# stat that's extremely costly and triggers automatic coalition response from
# every other kingdom, rather than an actually-simulated weapon -- this keeps
# the game about strategy/economy rather than needing real weapons design
# details, which isn't something to simulate mechanically.


def get_available_techs(unlocked: set) -> list:
    """Return tech ids the kingdom could start now (prereqs met, not yet unlocked)."""
    available = []
    for tech_id, data in TECH_TREE.items():
        if tech_id in unlocked:
            continue
        if all(p in unlocked for p in data["prereqs"]):
            available.append(tech_id)
    return available


def can_research(tech_id: str, unlocked: set) -> bool:
    if tech_id not in TECH_TREE:
        return False
    if tech_id in unlocked:
        return False
    return all(p in unlocked for p in TECH_TREE[tech_id]["prereqs"])

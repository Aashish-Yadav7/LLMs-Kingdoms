"""
Military units: build cost, monthly upkeep, required tech, and rough combat
power. Combat resolution is a simple stochastic model, not a full wargame --
good enough for turn-based strategic decisions, deliberately not a targeting
or weapons-effects simulator.
"""

import random

UNIT_TYPES = {
    "infantry": {
        "cost": 2_000_000, "upkeep": 50_000, "power": 1, "requires_tech": None,
    },
    "artillery": {
        "cost": 15_000_000, "upkeep": 300_000, "power": 4, "requires_tech": "combustion_engines",
    },
    "armored_vehicle": {
        "cost": 8_000_000, "upkeep": 200_000, "power": 3, "requires_tech": "armor_plating",
    },
    "main_battle_tank": {
        "cost": 25_000_000, "upkeep": 500_000, "power": 8, "requires_tech": "advanced_materials",
    },
    "rocket_artillery": {
        "cost": 40_000_000, "upkeep": 600_000, "power": 10, "requires_tech": "basic_rocketry",
    },
    "fighter_jet": {
        "cost": 120_000_000, "upkeep": 2_000_000, "power": 15, "requires_tech": "jet_propulsion",
    },
    "guided_missile": {
        "cost": 200_000_000, "upkeep": 500_000, "power": 25, "requires_tech": "guided_systems",
    },
    "destroyer": {
        "cost": 1_800_000_000, "upkeep": 15_000_000, "power": 30, "requires_tech": "naval_engineering",
    },
}


def can_build_unit(unit_type: str, unlocked_tech: set) -> bool:
    if unit_type not in UNIT_TYPES:
        return False
    req = UNIT_TYPES[unit_type]["requires_tech"]
    return req is None or req in unlocked_tech


def total_military_power(units: dict) -> int:
    return sum(UNIT_TYPES[u]["power"] * count for u, count in units.items() if u in UNIT_TYPES)


def total_upkeep(units: dict) -> int:
    return sum(UNIT_TYPES[u]["upkeep"] * count for u, count in units.items() if u in UNIT_TYPES)


def resolve_combat(attacker_units: dict, defender_units: dict, defender_terrain_bonus: float = 1.15):
    """
    Simple attrition model:
    - Compute total power on both sides (defender gets a terrain bonus).
    - The side with more effective power wins, loser takes proportional losses,
      winner takes lighter proportional losses.
    - Small random variance so outcomes aren't 100% deterministic.
    Returns a result dict describing losses on each side and the outcome.
    """
    atk_power = total_military_power(attacker_units) * random.uniform(0.9, 1.1)
    def_power = total_military_power(defender_units) * defender_terrain_bonus * random.uniform(0.9, 1.1)

    if atk_power <= 0 and def_power <= 0:
        return {"outcome": "no_combat", "attacker_losses": {}, "defender_losses": {}}

    total = atk_power + def_power
    attacker_win_chance = atk_power / total if total > 0 else 0.5

    attacker_wins = random.random() < attacker_win_chance

    # Loser loses 25-45% of forces, winner loses 5-15%
    def apply_losses(units: dict, fraction: float) -> dict:
        losses = {}
        for u, count in units.items():
            lost = int(count * fraction)
            if lost > 0:
                losses[u] = lost
        return losses

    if attacker_wins:
        attacker_losses = apply_losses(attacker_units, random.uniform(0.05, 0.15))
        defender_losses = apply_losses(defender_units, random.uniform(0.25, 0.45))
        outcome = "attacker_wins"
    else:
        attacker_losses = apply_losses(attacker_units, random.uniform(0.25, 0.45))
        defender_losses = apply_losses(defender_units, random.uniform(0.05, 0.15))
        outcome = "defender_wins"

    return {
        "outcome": outcome,
        "attacker_power": round(atk_power, 1),
        "defender_power": round(def_power, 1),
        "attacker_losses": attacker_losses,
        "defender_losses": defender_losses,
    }

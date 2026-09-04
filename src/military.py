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
    "aircraft_carrier": {
        "cost": 13_000_000_000, "upkeep": 90_000_000, "power": 60, "requires_tech": "aircraft_carrier_program",
    },
    "aerial_fortress": {
        "cost": 45_000_000_000, "upkeep": 300_000_000, "power": 150, "requires_tech": "aerial_fortress_program",
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


def resolve_combat(
    attacker_units: dict, defender_units: dict,
    attacker_morale: float = 100.0, defender_morale: float = 100.0,
    defender_terrain_bonus: float = 1.15,
):
    """
    Attrition model, now driven by morale as much as raw numbers:
    - Each side's effective power = raw military power * (morale / 100).
    - Morale ranges 0-150. A smaller force at 130 morale (defending home
      soil, riding a winning streak, popular cause) can out-fight a larger
      force at 60 morale (far from home, losing streak, unpopular war) --
      this is deliberate: real history is full of outnumbered defenders
      winning on exactly this dynamic, and raw unit count alone shouldn't
      decide outcomes here either.
    - Defender still gets a terrain bonus on top of their morale.
    - Small random variance so outcomes aren't 100% deterministic.
    Returns a result dict describing losses on each side and the outcome.
    """
    atk_morale_mult = max(0.0, attacker_morale) / 100
    def_morale_mult = max(0.0, defender_morale) / 100

    atk_power = total_military_power(attacker_units) * atk_morale_mult * random.uniform(0.9, 1.1)
    def_power = total_military_power(defender_units) * def_morale_mult * defender_terrain_bonus * random.uniform(0.9, 1.1)

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


def apply_post_combat_morale(winner_kingdom, loser_kingdom):
    """A win boosts patriotic fervor; a loss dents it. Called once per
    resolved battle. Morale is clamped 0-150 -- see Kingdom.morale."""
    winner_kingdom.morale = min(150.0, winner_kingdom.morale + 8.0)
    loser_kingdom.morale = max(10.0, loser_kingdom.morale - 12.0)


def morale_drift_tick(kingdom):
    """Called once per kingdom per turn (in economy.run_economy_tick).
    Morale drifts toward a target set by internal stability and how many
    active wars are being fought -- sustained war without victories grinds
    morale down over time (war-weariness); peace and high stability let it
    recover. This is a slow drift (10%/turn toward target), not an instant
    snap, so morale has real inertia."""
    target = 100.0 + (kingdom.stability - 80) * 0.3
    if kingdom.at_war_with:
        target -= 5.0 * len(kingdom.at_war_with)
    target = max(0.0, min(150.0, target))
    kingdom.morale += (target - kingdom.morale) * 0.1
    kingdom.morale = max(0.0, min(150.0, kingdom.morale))

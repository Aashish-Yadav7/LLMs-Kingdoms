"""
Economy tick: applied automatically by the engine every turn, before any AI
decisions. Kingdoms don't choose their tax rate via free text -- it's a bounded
numeric action validated here, so nobody can invent infinite money.
"""

from src.military import total_upkeep, total_military_power
from src.tech_tree import TECH_TREE

BASE_TAX_RATE_RANGE = (0.10, 0.45)  # kingdoms can set tax rate in this band
GDP_PER_CAPITA = 45_000  # baseline annual economic output per person, arbitrary but fixed
FOOD_CONSUMED_PER_CAPITA_PER_TURN = 0.9  # tons/person/turn
BASE_FOOD_PRODUCTION_PER_CAPITA = 1.05  # tons/person/turn, before tech bonuses

# --- Tax-driven unrest ---
# Real-world-ish framing: people tolerate a "normal" tax band without
# complaint. Above that, unrest builds every turn it's sustained; below a
# comfortable rate, stability slowly recovers. If stability collapses,
# a riot fires: population loss, treasury damage (unrest/property damage,
# money that's simply destroyed, not transferred), and military losses from
# units getting pulled into putting down unrest. A kingdom then has to
# actively spend to repair (see `apply_repair_investment` in orchestrator).
COMFORTABLE_TAX_MAX = 0.30
UNREST_RATE_PER_EXCESS_POINT = 3.2   # stability lost per turn, per 0.01 of tax above comfortable max
STABILITY_RECOVERY_PER_TURN = 2.5     # natural recovery per turn if tax is at/below comfortable max
RIOT_THRESHOLD = 25                    # stability at/below this triggers a riot
RIOT_POPULATION_LOSS_FRACTION = 0.02
RIOT_TREASURY_DAMAGE_FRACTION = 0.04
RIOT_MILITARY_LOSS_FRACTION = 0.10
RIOT_STABILITY_RESET_TO = 35           # after a riot, unrest partially burns itself out


def clamp_tax_rate(rate: float) -> float:
    lo, hi = BASE_TAX_RATE_RANGE
    return max(lo, min(hi, rate))


def run_economy_tick(kingdom) -> dict:
    """
    Mutates kingdom.treasury / food_storage / population / stability / units
    in place based on its current tax_rate and unit upkeep. Returns a summary
    dict for logging.
    """
    tax_rate = clamp_tax_rate(kingdom.tax_rate)
    gross_output = kingdom.population * GDP_PER_CAPITA / 12  # per-turn slice of annual GDP

    transport_bonus = 1.15 if "transport_infrastructure" in kingdom.unlocked_tech else 1.0
    refining_bonus = 1.10 if "petrochemical_refining" in kingdom.unlocked_tech else 1.0
    tax_income = gross_output * tax_rate * transport_bonus * refining_bonus

    upkeep_cost = total_upkeep(kingdom.units)

    food_bonus = 1.0
    if "agri_automation" in kingdom.unlocked_tech:
        food_bonus += 0.30
    food_produced = kingdom.population * BASE_FOOD_PRODUCTION_PER_CAPITA * food_bonus
    food_needed = kingdom.population * FOOD_CONSUMED_PER_CAPITA_PER_TURN
    food_delta = food_produced - food_needed

    energy_discount = 0.8 if "renewable_grid" in kingdom.unlocked_tech else 1.0
    infra_upkeep = kingdom.population * 120 * energy_discount  # baseline infrastructure cost

    net_change = tax_income - upkeep_cost - infra_upkeep

    kingdom.treasury += net_change
    kingdom.food_storage += food_delta

    # Starvation consequence: if food storage goes negative, population and
    # stability suffer -- money alone cannot fix a starving population instantly.
    starving = kingdom.food_storage < 0
    if starving:
        population_loss = int(kingdom.population * 0.01)
        kingdom.population = max(0, kingdom.population - population_loss)
        kingdom.food_storage = 0
        kingdom.stability = max(0, kingdom.stability - 5)
    else:
        population_growth = int(kingdom.population * 0.0015)
        kingdom.population += population_growth

    # --- Tax-driven unrest ---
    if tax_rate > COMFORTABLE_TAX_MAX:
        excess_points = (tax_rate - COMFORTABLE_TAX_MAX) * 100  # e.g. 0.45 - 0.30 = 0.15 -> 15 points
        kingdom.stability = max(0, kingdom.stability - excess_points * UNREST_RATE_PER_EXCESS_POINT / 10)
    else:
        kingdom.stability = min(100, kingdom.stability + STABILITY_RECOVERY_PER_TURN)

    riot = None
    if kingdom.stability <= RIOT_THRESHOLD:
        pop_lost = int(kingdom.population * RIOT_POPULATION_LOSS_FRACTION)
        treasury_lost = kingdom.treasury * RIOT_TREASURY_DAMAGE_FRACTION
        kingdom.population = max(0, kingdom.population - pop_lost)
        kingdom.treasury = max(0, kingdom.treasury - treasury_lost)

        units_lost = {}
        for unit_type, count in list(kingdom.units.items()):
            lost = int(count * RIOT_MILITARY_LOSS_FRACTION)
            if lost > 0:
                kingdom.units[unit_type] = count - lost
                units_lost[unit_type] = lost
        # units lost proportionally also removed from wherever they're stationed
        if units_lost:
            for province_units in kingdom.unit_positions.values():
                for unit_type, lost in units_lost.items():
                    if unit_type in province_units and province_units[unit_type] > 0:
                        cut = min(province_units[unit_type], max(1, lost // max(1, len(kingdom.unit_positions))))
                        province_units[unit_type] -= cut

        kingdom.stability = RIOT_STABILITY_RESET_TO
        riot = {
            "population_lost": pop_lost,
            "treasury_damage": round(treasury_lost, 2),
            "units_lost": units_lost,
        }

    return {
        "tax_rate": round(tax_rate, 3),
        "tax_income": round(tax_income, 2),
        "upkeep_cost": round(upkeep_cost, 2),
        "infra_upkeep": round(infra_upkeep, 2),
        "net_treasury_change": round(net_change, 2),
        "food_delta": round(food_delta, 2),
        "starving": starving,
        "treasury_after": round(kingdom.treasury, 2),
        "population_after": kingdom.population,
        "stability_after": round(kingdom.stability, 1),
        "riot": riot,
    }


def apply_repair_investment(kingdom, amount: float) -> dict:
    """
    A kingdom can spend money to actively rebuild after unrest/riots instead
    of just waiting for natural recovery. Every $50B committed restores 1
    stability point, capped at +20 stability per turn and never above 100.
    Returns how much was actually spent/gained (amount may be reduced if the
    kingdom can't afford what it proposed).
    """
    if amount <= 0:
        return {"spent": 0, "stability_gained": 0}
    amount = min(amount, kingdom.treasury)
    stability_gain = min(20, amount / 50_000_000_000)
    stability_gain = min(stability_gain, 100 - kingdom.stability)
    actual_cost = stability_gain * 50_000_000_000
    kingdom.treasury -= actual_cost
    kingdom.stability = min(100, kingdom.stability + stability_gain)
    return {"spent": round(actual_cost, 2), "stability_gained": round(stability_gain, 1)}


def research_tick(kingdom) -> dict:
    """Advance any in-progress research by one turn if funded.
    research_speed_multiplier lets a kingdom progress faster than 1 turn's
    worth per turn (used for player_llm's strategic edge)."""
    if not kingdom.researching:
        return {"status": "idle"}

    tech_id = kingdom.researching
    tech = TECH_TREE[tech_id]
    kingdom.research_progress += getattr(kingdom, "research_speed_multiplier", 1.0)

    if kingdom.research_progress >= tech["research_turns"]:
        kingdom.unlocked_tech.add(tech_id)
        kingdom.researching = None
        kingdom.research_progress = 0
        return {"status": "completed", "tech": tech_id}

    return {
        "status": "in_progress",
        "tech": tech_id,
        "progress": round(kingdom.research_progress, 1),
        "needed": tech["research_turns"],
    }

"""
Economy tick: applied automatically by the engine every turn, before any AI
decisions. Kingdoms don't choose their tax rate via free text -- it's a bounded
numeric action validated here, so nobody can invent infinite money.
"""

from src.military import total_upkeep
from src.tech_tree import TECH_TREE

BASE_TAX_RATE_RANGE = (0.10, 0.45)  # kingdoms can set tax rate in this band
GDP_PER_CAPITA = 45_000  # baseline annual economic output per person, arbitrary but fixed
FOOD_CONSUMED_PER_CAPITA_PER_TURN = 0.9  # tons/person/turn
BASE_FOOD_PRODUCTION_PER_CAPITA = 1.05  # tons/person/turn, before tech bonuses


def clamp_tax_rate(rate: float) -> float:
    lo, hi = BASE_TAX_RATE_RANGE
    return max(lo, min(hi, rate))


def run_economy_tick(kingdom) -> dict:
    """
    Mutates kingdom.treasury / food_storage / population in place based on its
    current tax_rate and unit upkeep. Returns a summary dict for logging.
    """
    tax_rate = clamp_tax_rate(kingdom.tax_rate)
    gross_output = kingdom.population * GDP_PER_CAPITA / 12  # per-turn slice of annual GDP
    tax_income = gross_output * tax_rate

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
    }


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

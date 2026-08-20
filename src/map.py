"""
Loads data/map.json and generates each region's resource deposits, using
real-world strategic resources/elements rather than abstract placeholders.

Rules (per your instructions):
- South pole ("player_llm" owner): EVERY resource type, guaranteed present,
  at the highest density on the map -- the richest territory by design.
- The four top continents (one per AI kingdom): every resource type CAN
  appear, at lower odds and smaller quantities, tuned so each continent's
  total stockpile lands around ~15,000-17,000 units -- rich enough to build
  a real economy, nowhere near the south pole's abundance.
- Unclaimed mid-ocean islands: sparse, randomized, belong to nobody at game
  start -- any kingdom can send forces to explore and claim them.
"""

import json
import random
from pathlib import Path

MAP_PATH = Path(__file__).parent.parent / "data" / "map.json"

# Real-world strategic resources/elements. Covers energy, base + precious
# metals, fissile materials, and the two "soft" resources (timber/water/land)
# that feed the economy layer.
RESOURCE_TYPES = [
    # energy
    "coal", "oil", "natural_gas", "uranium", "plutonium",
    # base metals
    "iron", "copper", "aluminum", "zinc", "nickel", "cobalt", "titanium",
    # precious / strategic metals
    "gold", "silver", "platinum", "lithium", "rare_earth_elements",
    # land/agriculture
    "timber", "fresh_water", "arable_land",
]

# density -> (chance a given province has a given resource, min-max quantity if present)
DENSITY_PROFILES = {
    "very_high": {"chance": 1.00, "range": (900, 1300)},   # south pole: everything, guaranteed, abundant
    "medium":    {"chance": 0.48, "range": (230, 420)},     # AI continents: partial, tuned for ~15-17k totals
    "low":       {"chance": 0.30, "range": (50, 200)},      # unclaimed islands: sparse
}


def load_map() -> dict:
    return json.loads(MAP_PATH.read_text())


def generate_province_resources(density: str) -> dict:
    """Return {resource_type: quantity} for one province, possibly empty for some types."""
    profile = DENSITY_PROFILES[density]
    deposits = {}
    for res in RESOURCE_TYPES:
        if random.random() < profile["chance"]:
            deposits[res] = random.randint(*profile["range"])
    return deposits


def build_world_resources(rng_seed: int = 42) -> dict:
    """
    Returns full resource layout for every province on the map:
    {
      "continents": {continent_id: {"owner": ..., "provinces": {province_id: {resources...}}}},
      "unclaimed_islands": {island_id: {resources...}}
    }
    Deterministic given rng_seed, so the same seed always produces the same
    starting world -- change the seed for a different random world each game.
    """
    random.seed(rng_seed)
    world = json.loads(MAP_PATH.read_text())
    layout = {"continents": {}, "unclaimed_islands": {}}

    for cont_id, cont in world["continents"].items():
        density = cont["resource_density"]
        provinces = {}
        for prov in cont["provinces"]:
            provinces[prov["id"]] = {
                "name": prov["name"],
                "terrain": prov["terrain"],
                "resources": generate_province_resources(density),
            }
        layout["continents"][cont_id] = {
            "owner": cont["owner"],
            "display_name": cont["display_name"],
            "provinces": provinces,
        }

    for isle in world["unclaimed_islands"]:
        layout["unclaimed_islands"][isle["id"]] = {
            "name": isle["name"],
            "terrain": isle["terrain"],
            "resources": generate_province_resources("low"),
            "controlled_by": None,  # kingdom id once claimed, else None
        }

    return layout


def continent_total_resources(layout: dict, continent_id: str) -> dict:
    """Sum all resource quantities across a continent's provinces -- what a kingdom starts with."""
    totals = {}
    for prov in layout["continents"][continent_id]["provinces"].values():
        for res, qty in prov["resources"].items():
            totals[res] = totals.get(res, 0) + qty
    return totals


def capital_province(continent_id: str) -> str:
    """First province listed for a continent -- used as the default staging
    point where newly built units appear."""
    world = json.loads(MAP_PATH.read_text())
    return world["continents"][continent_id]["provinces"][0]["id"]


def continent_province_ids(continent_id: str) -> list:
    world = json.loads(MAP_PATH.read_text())
    return [p["id"] for p in world["continents"][continent_id]["provinces"]]


def province_owner(province_id: str, world: dict | None = None) -> str | None:
    """Kingdom id that owns this province's continent, or None if it's an
    unclaimed island (or an unrecognized id). Ownership here is tracked at
    the continent level -- there's no per-province conquest/capture yet,
    so a battle won on foreign soil doesn't currently change who 'owns' it.
    """
    world = world or load_map()
    for cont_id, cont in world["continents"].items():
        if any(p["id"] == province_id for p in cont["provinces"]):
            return cont["owner"]
    return None  # unclaimed island, or unknown id


def is_island(province_id: str, world: dict | None = None) -> bool:
    world = world or load_map()
    return any(isle["id"] == province_id for isle in world["unclaimed_islands"])


def provinces_adjacent(a: str, b: str, world: dict | None = None) -> bool:
    """True if a and b directly border each other per data/map.json's
    'borders' lists. This is the only way a single move_units action can
    move (or attack) from one location to another -- no teleporting across
    the map in one turn, and no attacking a kingdom you can't reach yet."""
    world = world or load_map()
    borders = _province_borders_index(world)
    return b in borders.get(a, set()) or a in borders.get(b, set())


def province_borders(province_id: str, world: dict | None = None) -> list:
    """List of province/island ids directly adjacent to this one -- the
    only valid single-hop move/attack targets from here."""
    world = world or load_map()
    return sorted(_province_borders_index(world).get(province_id, set()))


def _province_borders_index(world: dict) -> dict:
    index = {}
    for cont in world["continents"].values():
        for p in cont["provinces"]:
            index[p["id"]] = set(p.get("borders", []))
    for isle in world["unclaimed_islands"]:
        index[isle["id"]] = set(isle.get("borders", []))
    return index

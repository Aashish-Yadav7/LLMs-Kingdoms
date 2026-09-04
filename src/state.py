"""
Core state objects. Kept as plain dataclasses + JSON so the whole game state
is trivially saveable/loadable/diffable, and easy to hand to an LLM as
structured context.
"""

from dataclasses import dataclass, field, asdict
import json
from pathlib import Path

from src.config import STARTING_TREASURY, STARTING_POPULATION, STARTING_FOOD_STORAGE


@dataclass
class Kingdom:
    id: str
    name: str
    model: str
    personality: str

    treasury: float = STARTING_TREASURY
    population: int = STARTING_POPULATION
    food_storage: float = STARTING_FOOD_STORAGE
    stability: int = 80  # 0-100, low stability = unrest, eventually revolt (future extension)

    tax_rate: float = 0.25
    units: dict = field(default_factory=dict)  # {"infantry": 1000, ...}

    unlocked_tech: set = field(default_factory=lambda: {"basic_industry"})
    researching: str | None = None
    research_progress: int = 0

    alliances: list = field(default_factory=list)  # list of kingdom ids
    at_war_with: list = field(default_factory=list)  # list of kingdom ids

    home_continent: str = ""  # continent id from data/map.json
    resources: dict = field(default_factory=dict)  # {"iron": 4200, "oil": 1800, ...} -- starting stockpile from home continent
    unit_positions: dict = field(default_factory=dict)  # province_id -> {"infantry": 100, ...} -- where units are actually stationed
    research_speed_multiplier: float = 1.0  # >1.0 = researches faster; used for player_llm's edge

    custom_researching: dict | None = None  # {"name":..., "description":..., "category":..., "cost":..., "turns_needed":..., "progress":...}
    custom_projects: list = field(default_factory=list)  # completed custom inventions: [{"name", "description", "category", "cost", "power_rating"}]

    # --- Discovery (fog of war) ---
    # Every kingdom starts knowing NO ONE exists but itself -- not even that
    # other kingdoms are out there. Only after unlocking "basic_navigation"
    # can a kingdom start discovering others (see economy.run_discovery_tick).
    # A kingdom that hasn't discovered another cannot see it, speak to it in
    # conference, or be seen/spoken to by it -- true mutual fog of war.
    known_kingdoms: set = field(default_factory=set)  # kingdom ids this kingdom has discovered

    # --- Morale (distinct from `stability`) ---
    # `stability` is internal political calm; `morale` is the army's actual
    # fighting spirit/patriotism, and is what combat power scales with. A
    # smaller, high-morale force (defending home soil, high public support)
    # can beat a larger, low-morale one (far from home, losing streak,
    # unpopular war) -- matching how real militarily-outnumbered defenders
    # have repeatedly won historically. Range 0-150; 100 is baseline.
    morale: float = 100.0

    # --- Colonization ---
    # province_id -> {"colonizer": kid, "since_turn": N} for provinces this
    # kingdom has colonized that belong to ANOTHER kingdom's home continent.
    # Tribute is extracted from these each economy tick (see economy.py).
    colonies: dict = field(default_factory=dict)

    def public_summary(self) -> dict:
        """What OTHER kingdoms are allowed to see about this one.
        Resources are shown as an approximate number (real intel estimate,
        noisy +/-12%), not an exact figure and not a vague tier -- enough for
        other kingdoms to actually plan strategy around, without knowing your
        precise stockpile."""
        return {
            "id": self.id,
            "name": self.name,
            "home_continent": self.home_continent,
            "approx_treasury_tier": _treasury_tier(self.treasury),
            "approx_military_tier": _military_tier(self.units),
            "approx_resource_total": _resource_approx(self.resources),
            "population": self.population,
            "alliances": self.alliances,
            "at_war_with": self.at_war_with,
            "known_tech_count": len(self.unlocked_tech),
        }

    def intel_view(self, viewer_id: str) -> dict:
        """What THIS kingdom reveals to a specific viewer. Every kingdom sees
        the standard noisy public_summary of everyone else -- except player_llm,
        which sees exact figures on every other kingdom (treasury, resources,
        units, current research). This asymmetry exists only in what data is
        assembled here; it is never mentioned in any other kingdom's prompt."""
        if viewer_id == "player_llm":
            return {
                "id": self.id,
                "name": self.name,
                "home_continent": self.home_continent,
                "treasury": round(self.treasury, 2),
                "population": self.population,
                "resources": dict(self.resources),
                "units": dict(self.units),
                "unlocked_tech": sorted(self.unlocked_tech),
                "researching": self.researching,
                "alliances": self.alliances,
                "at_war_with": self.at_war_with,
            }
        return self.public_summary()

    def private_summary(self) -> dict:
        """Full detail, only ever shown to this kingdom's own agent."""
        d = asdict(self)
        d["unlocked_tech"] = sorted(self.unlocked_tech)
        return d


def _treasury_tier(treasury: float) -> str:
    if treasury > 200_000_000_000_000:
        return "vast"
    if treasury > 80_000_000_000_000:
        return "strong"
    if treasury > 20_000_000_000_000:
        return "moderate"
    if treasury > 0:
        return "strained"
    return "bankrupt"


def _resource_approx(resources: dict) -> int:
    """Simulates other kingdoms' intelligence estimate of total resource
    stockpile: real number, rounded, with +/-12% noise -- close enough to plan
    around, not exact enough to know your true position."""
    import random
    total = sum(resources.values()) if resources else 0
    noisy = total * random.uniform(0.88, 1.12)
    return int(round(noisy / 100) * 100)


def _military_tier(units: dict) -> str:
    from src.military import total_military_power
    power = total_military_power(units)
    if power > 5000:
        return "dominant"
    if power > 1500:
        return "strong"
    if power > 300:
        return "moderate"
    if power > 0:
        return "minimal"
    return "none"


@dataclass
class GameState:
    turn: int = 0
    kingdoms: dict = field(default_factory=dict)  # id -> Kingdom
    conference_log: list = field(default_factory=list)  # this turn's public messages
    secret_meeting_log: dict = field(default_factory=dict)  # pair_key -> list of messages
    history: list = field(default_factory=list)  # turn summaries for narrative continuity
    unclaimed_islands: dict = field(default_factory=dict)  # island_id -> {resources, controlled_by, ...}
    turn_reasoning: dict = field(default_factory=dict)  # kingdom_id -> reasoning string, THIS turn only (spectator-only view of AI thinking)
    # province_id -> kingdom_id -- the REAL, mutable owner of every province.
    # Starts matching data/map.json's static continent owners, but can change
    # through colonization. Combat, colonization, and the map viewer all read
    # ownership from here, never from map.json directly, once the game starts.
    province_owners: dict = field(default_factory=dict)

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "turn": self.turn,
            "kingdoms": {
                kid: {
                    **asdict(k),
                    "unlocked_tech": sorted(k.unlocked_tech),
                    "known_kingdoms": sorted(k.known_kingdoms),
                }
                for kid, k in self.kingdoms.items()
            },
            "conference_log": self.conference_log,
            "secret_meeting_log": self.secret_meeting_log,
            "history": self.history,
            "unclaimed_islands": self.unclaimed_islands,
            "province_owners": self.province_owners,
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> "GameState":
        data = json.loads(Path(path).read_text())
        gs = cls(turn=data["turn"])
        for kid, kdata in data["kingdoms"].items():
            kdata = dict(kdata)
            kdata["unlocked_tech"] = set(kdata["unlocked_tech"])
            kdata["known_kingdoms"] = set(kdata.get("known_kingdoms", []))
            gs.kingdoms[kid] = Kingdom(**kdata)
        gs.conference_log = data.get("conference_log", [])
        gs.secret_meeting_log = data.get("secret_meeting_log", {})
        gs.history = data.get("history", [])
        gs.unclaimed_islands = data.get("unclaimed_islands", {})
        gs.province_owners = data.get("province_owners", {})
        return gs

    @classmethod
    def new_game(cls) -> "GameState":
        from src.config import (
            KINGDOMS, KINGDOM_CONTINENTS, MAP_RNG_SEED,
            PLAYER_LLM_RESEARCH_SPEED_MULTIPLIER, PLAYER_LLM_STARTING_TECH,
        )
        from src.map import build_world_resources, continent_total_resources, capital_province

        gs = cls(turn=0)
        world_layout = build_world_resources(rng_seed=MAP_RNG_SEED)

        for kid, cfg in KINGDOMS.items():
            continent_id = KINGDOM_CONTINENTS[kid]
            starting_resources = continent_total_resources(world_layout, continent_id)
            kingdom = Kingdom(
                id=kid,
                name=cfg["name"],
                model=cfg["model"],
                personality=cfg["personality"],
                home_continent=continent_id,
                resources=starting_resources,
            )
            if kid == "player_llm":
                kingdom.unlocked_tech = set(PLAYER_LLM_STARTING_TECH)
                kingdom.research_speed_multiplier = PLAYER_LLM_RESEARCH_SPEED_MULTIPLIER
            gs.kingdoms[kid] = kingdom

        gs.unclaimed_islands = world_layout["unclaimed_islands"]

        # Province ownership starts matching each kingdom's home continent,
        # but is now a mutable, per-game fact (not read from map.json at
        # runtime) so colonization can actually change hands.
        import json as _json
        from pathlib import Path as _Path
        world = _json.loads((_Path(__file__).parent.parent / "data" / "map.json").read_text())
        for cont_id, cont in world["continents"].items():
            owner_kid = cont["owner"]
            for prov in cont["provinces"]:
                gs.province_owners[prov["id"]] = owner_kid

        return gs


def find_latest_save(save_dir: str = "data") -> Path | None:
    """Finds the highest-numbered save_turn_N.json in save_dir, or None if
    there isn't one. Shared by main.py and tests/mock_playthrough.py so a
    plain run automatically continues an existing game instead of starting
    over from scratch every time."""
    save_path = Path(save_dir)
    if not save_path.exists():
        return None
    saves = list(save_path.glob("save_turn_*.json"))
    if not saves:
        return None

    def turn_number(p: Path) -> int:
        try:
            return int(p.stem.split("_")[-1])
        except ValueError:
            return -1

    return max(saves, key=turn_number)

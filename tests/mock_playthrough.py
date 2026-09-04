"""
Runs a full game loop with fake, scripted agents instead of real LLM calls.
Use this to confirm the engine (economy, tech, builds, movement, combat,
diplomacy, discovery, colonization, map rendering) all work correctly
before spending any API budget.

Run from the project root:
    python tests/mock_playthrough.py
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from src.state import GameState
from src.orchestrator import run_turn


class MockAgent:
    """Fakes an LLM's decisions with simple scripted/random behavior -- just
    enough variety to exercise every part of the engine (builds, research,
    discovery, movement, diplomacy, colonization, combat) without calling
    any API.

    Every kingdom researches basic_navigation first (required before any
    diplomacy or discovery can happen at all), then falls back to
    combustion_engines once that's done.

    'north' and 'east' are bootstrapped to already know about each other
    (real games discover each other gradually and probabilistically -- see
    economy.run_discovery_tick -- but that's too random to script a
    reliable demo turn-by-turn, so this one pair is seeded directly). Every
    OTHER kingdom pair still discovers each other organically through the
    normal probabilistic system, so the fog-of-war mechanic is still
    genuinely exercised, just not left to chance for this one scripted
    invasion-and-colonization demo:

    Turn 3: 'north' declares war on 'east'.
    Turns 4-6: 'north' marches infantry along the real adjacency chain
      (north_1 -> north_5 -> isle_1 -> east_1), landing on east's soil.
    Turn 7: 'north' attempts to colonize east_1 if it's undefended.
    Run with --turns 10 or more to see the whole arc, including a turn or
    two of colonial tribute income afterward.
    """

    def __init__(self, kid, game_state):
        self.kid = kid
        self.game_state = game_state

    def decide(self, prompt, schema_hint):
        if "SECRET meeting" in prompt:
            return {"message": f"({self.kid}) proposing a trade route between our kingdoms."}
        if "secret, private meeting" in prompt:
            return {"accept": random.random() < 0.6}
        if "public conference" in prompt:
            return {
                "speak": random.random() < 0.4,
                "message": f"Greetings from {self.kid}. We seek prosperity, not conflict.",
            }

        kingdom = self.game_state.kingdoms[self.kid]
        turn = self.game_state.turn  # run_turn() increments turn before agents decide

        research = None
        if "basic_navigation" not in kingdom.unlocked_tech and not kingdom.researching:
            research = "basic_navigation"
        elif "combustion_engines" not in kingdom.unlocked_tech and not kingdom.researching:
            research = "combustion_engines"

        decision = {
            "tax_rate": round(random.uniform(0.18, 0.32), 2),
            "research": research,
            "build_units": {"infantry": random.randint(50, 200)},
            "move_units": None,
            "repair_investment": None,
            "custom_project": None,
            "colonize_province": None,
            "secret_meeting_request": None,
            "declare_war_on": None,
            "reasoning": "mock agent test action",
        }

        if self.kid == "north":
            if turn == 3:
                decision["declare_war_on"] = "east"
                decision["reasoning"] = "scripted: opening hostilities with east"
            elif turn == 4:
                decision["move_units"] = {"from": "north_1", "to": "north_5", "unit_type": "infantry", "count": 150}
                decision["reasoning"] = "scripted: marching the invasion force from the capital to the frontier"
            elif turn == 5:
                decision["move_units"] = {"from": "north_5", "to": "isle_1", "unit_type": "infantry", "count": 150}
                decision["reasoning"] = "scripted: staging at the isle_1 chokepoint"
            elif turn == 6:
                decision["move_units"] = {"from": "isle_1", "to": "east_1", "unit_type": "infantry", "count": 150}
                decision["reasoning"] = "scripted: landing the invasion on east's soil -- combat should trigger"
            elif turn >= 7:
                decision["colonize_province"] = "east_1"
                decision["reasoning"] = "scripted: attempting to colonize east's capital if it's undefended"

        return decision


def main():
    import argparse
    from pathlib import Path as _Path
    parser = argparse.ArgumentParser(description="Run a mock (no-API) playthrough to test the engine.")
    parser.add_argument("--turns", type=int, default=10, help="How many MORE turns to play from wherever the game currently is")
    parser.add_argument("--new", action="store_true", help="Force a brand new game even if a save already exists")
    args = parser.parse_args()

    print("=== Kingdoms AI: mock playthrough (no API calls) ===\n")

    existing_saves = sorted(_Path("data").glob("save_turn_*.json"),
                             key=lambda p: int(p.stem.split("_")[-1])) if _Path("data").exists() else []
    if args.new or not existing_saves:
        game_state = GameState.new_game()
        # Seed north<->east discovery so the scripted invasion demo below is
        # reliable turn-to-turn -- every OTHER pair still discovers each
        # other organically via the normal probabilistic system.
        game_state.kingdoms["north"].unlocked_tech.add("basic_navigation")
        game_state.kingdoms["east"].unlocked_tech.add("basic_navigation")
        game_state.kingdoms["north"].known_kingdoms.add("east")
        game_state.kingdoms["east"].known_kingdoms.add("north")
        print("Starting a new game." if not existing_saves else "Starting a NEW game (--new was passed, ignoring existing save).")
    else:
        game_state = GameState.load(str(existing_saves[-1]))
        print(f"Resuming from {existing_saves[-1]}, currently at turn {game_state.turn}. "
              f"Will play turns {game_state.turn + 1} through {game_state.turn + args.turns}.")

    print("\nKingdoms:")
    for kid, k in game_state.kingdoms.items():
        total_res = sum(k.resources.values())
        print(f"  {kid:12s} | {k.name:22s} | continent={k.home_continent:12s} | "
              f"treasury=${k.treasury:,.0f} | resources={total_res:,}")
    print()

    agents = {kid: MockAgent(kid, game_state) for kid in game_state.kingdoms}

    for turn in range(args.turns):
        print(f"--- Running turn {game_state.turn + 1} ---")
        run_turn(game_state, agents, log_dir="logs")
        save_path = f"data/save_turn_{game_state.turn}.json"
        game_state.save(save_path)
        print(f"  saved -> {save_path}")
        print(f"  log   -> logs/turn_{game_state.turn}.md\n")

    print("=== Done. Opening maps/game.html (all turns, one window) in your browser... ===")
    import webbrowser
    webbrowser.open(_Path("maps/game.html").resolve().as_uri())


if __name__ == "__main__":
    main()

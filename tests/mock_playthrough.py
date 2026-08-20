"""
Runs a full game loop with fake, scripted agents instead of real LLM calls.
Use this to confirm the engine (economy, tech, builds, movement, combat,
diplomacy, map rendering) all work correctly before spending any API budget.

Run from the project root:
    python tests/mock_playthrough.py
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # allow `from src...` imports when run directly

# Same Windows cp1252-vs-emoji fix as main.py
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from src.state import GameState
from src.orchestrator import run_turn


class MockAgent:
    """Fakes an LLM's decisions with simple scripted/random behavior -- just
    enough variety to exercise every part of the engine (builds, research,
    movement, diplomacy, occasional war) without calling any API.

    Turns 1-2: everyone builds up infantry at their capital (north's capital
      is north_1, the first province in data/map.json's north list).
    Turn 3: 'north' declares war on 'east'.
    Turns 4-6: 'north' marches infantry along the real adjacency chain
      (north_1 -> north_5 -> isle_1 -> east_1), exercising multi-hop
      movement and, once it lands on east's soil while at war,
      position-based combat.
    This is scripted around this repo's actual data/map.json borders, so if
    the map data ever changes, update the path below to match. Run with
    --turns 7 or more to see it play out (war on turn 3, landing on turn 6,
    combat visible in logs/turn_6.md).
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

        turn = self.game_state.turn  # run_turn() increments turn before agents decide
        decision = {
            "tax_rate": round(random.uniform(0.18, 0.32), 2),
            "research": "combustion_engines",
            "build_units": {"infantry": random.randint(50, 200)},
            "move_units": None,
            "repair_investment": None,
            "custom_project": None,
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

        return decision


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run a mock (no-API) playthrough to test the engine.")
    parser.add_argument("--turns", type=int, default=10, help="How many turns to simulate (default 10, minimum 6 to see the scripted invasion play out)")
    args = parser.parse_args()

    print("=== Kingdoms AI: mock playthrough (no API calls) ===\n")
    game_state = GameState.new_game()

    print("Starting kingdoms:")
    for kid, k in game_state.kingdoms.items():
        total_res = sum(k.resources.values())
        print(f"  {kid:12s} | {k.name:22s} | continent={k.home_continent:12s} | "
              f"treasury=${k.treasury:,.0f} | resources={total_res:,}")
    print()

    agents = {kid: MockAgent(kid, game_state) for kid in game_state.kingdoms}

    for turn in range(args.turns):
        print(f"--- Running turn {turn + 1}/{args.turns} ---")
        run_turn(game_state, agents, log_dir="logs")
        save_path = f"data/save_turn_{game_state.turn}.json"
        game_state.save(save_path)
        print(f"  saved -> {save_path}")
        print(f"  log   -> logs/turn_{game_state.turn}.md")
        print(f"  map   -> maps/turn_{game_state.turn}.html (also maps/latest.html)\n")

    print("=== Done. Opening maps/latest.html in your browser... ===")
    import webbrowser
    from pathlib import Path as _Path
    webbrowser.open(_Path("maps/latest.html").resolve().as_uri())


if __name__ == "__main__":
    main()

import argparse
import sys
from pathlib import Path

# Windows terminals often default to cp1252, which can't print emoji/unicode
# used in map rendering and logs. Force UTF-8 on stdout so nothing crashes
# or garbles when this runs on Windows.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

from src.state import GameState, find_latest_save
from src.orchestrator import run_turn, build_agents

load_dotenv()
console = Console()


def main():
    parser = argparse.ArgumentParser(description="Run the Kingdoms AI game.")
    parser.add_argument("--turns", type=int, default=1, help="How many MORE turns to play from wherever the game currently is")
    parser.add_argument("--load", type=str, default=None, help="Path to a specific save file to resume from (overrides auto-resume)")
    parser.add_argument("--new", action="store_true", help="Force a brand new game even if a save already exists")
    parser.add_argument("--save-dir", type=str, default="data", help="Directory for autosaves")
    parser.add_argument("--log-dir", type=str, default="logs", help="Directory for turn logs")
    args = parser.parse_args()

    if args.load:
        game_state = GameState.load(args.load)
        console.print(f"[bold]Loaded save from {args.load}, resuming at turn {game_state.turn}[/bold]")
    elif args.new:
        game_state = GameState.new_game()
        console.print("[bold]Starting a brand new game (--new was passed).[/bold]")
    else:
        latest = find_latest_save(args.save_dir)
        if latest:
            game_state = GameState.load(str(latest))
            console.print(
                f"[bold]Resuming existing game from {latest} -- currently at turn {game_state.turn}. "
                f"Will play turns {game_state.turn + 1} through {game_state.turn + args.turns}.[/bold]"
            )
        else:
            game_state = GameState.new_game()
            console.print("[bold]No existing save found -- starting a new game.[/bold]")

    agents = build_agents(game_state)

    for _ in range(args.turns):
        log_text = run_turn(game_state, agents, log_dir=args.log_dir)
        console.print(Markdown(log_text))
        save_path = str(Path(args.save_dir) / f"save_turn_{game_state.turn}.json")
        game_state.save(save_path)
        console.print(f"[dim]Saved to {save_path}[/dim]\n")

    console.print("[bold]Opening the god view in your browser...[/bold]")
    import webbrowser
    webbrowser.open(Path("maps/game.html").resolve().as_uri())


if __name__ == "__main__":
    main()

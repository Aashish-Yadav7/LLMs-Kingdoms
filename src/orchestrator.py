"""
The turn loop. This is the referee: it runs the economy automatically,
lets each kingdom's LLM plan and negotiate, then validates and applies
every submitted action against the real game rules. No AI output is ever
trusted blindly -- everything with a cost is checked against treasury/tech.
"""

from pathlib import Path

from src.economy import run_economy_tick, research_tick
from src.military import UNIT_TYPES, can_build_unit, resolve_combat
from src.tech_tree import TECH_TREE, can_research, get_available_techs
from src.diplomacy import run_conference, run_secret_meetings
from src.agents.llm_agent import LLMAgent
from src.map import capital_province, continent_province_ids


def build_agents(game_state) -> dict:
    agents = {}
    for kid, kingdom in game_state.kingdoms.items():
        agents[kid] = LLMAgent(kingdom.model, kingdom.name, kingdom.personality)
    return agents


def run_turn(game_state, agents: dict, log_dir: str = "logs") -> str:
    game_state.turn += 1
    log_lines = [f"# Turn {game_state.turn}\n"]

    # 1. Economy tick (automatic, no AI involved)
    log_lines.append("## Economy\n")
    for kid, kingdom in game_state.kingdoms.items():
        summary = run_economy_tick(kingdom)
        research_summary = research_tick(kingdom)
        log_lines.append(
            f"- **{kingdom.name}**: treasury ${summary['treasury_after']:,.0f}, "
            f"pop {summary['population_after']:,}, "
            f"tax income ${summary['tax_income']:,.0f}, "
            f"upkeep ${summary['upkeep_cost']:,.0f}"
            + (" — ⚠️ FOOD SHORTAGE" if summary["starving"] else "")
        )
        if research_summary["status"] == "completed":
            log_lines.append(f"  - Research complete: **{research_summary['tech']}**")

    # 2. Private planning: each kingdom decides its economic/military/research
    #    action, plus who (if anyone) it wants a secret meeting with.
    log_lines.append("\n## Private Decisions\n")
    secret_requests = {}
    planned_actions = {}
    for kid, kingdom in game_state.kingdoms.items():
        others = [k.intel_view(kid) for oid, k in game_state.kingdoms.items() if oid != kid]
        available_techs = get_available_techs(kingdom.unlocked_tech)
        buildable_units = [u for u in UNIT_TYPES if can_build_unit(u, kingdom.unlocked_tech)]
        own_provinces = continent_province_ids(kingdom.home_continent)

        prompt = (
            f"Turn {game_state.turn}. Your private state:\n{kingdom.private_summary()}\n\n"
            f"Other kingdoms (info available to you):\n{others}\n\n"
            f"Techs you could start researching now: {available_techs}\n"
            f"Unit types you can currently build: {buildable_units}\n"
            f"Unit costs/upkeep reference: { {u: {'cost': d['cost'], 'upkeep': d['upkeep']} for u, d in UNIT_TYPES.items()} }\n"
            f"Your provinces (for troop movement): {own_provinces}\n"
            f"Current unit deployment by province: {kingdom.unit_positions}\n\n"
            "Decide this turn's action. You may set your tax rate (0.10-0.45), "
            "start researching one tech (or continue current research), "
            "build units (limited by treasury; new units appear at your capital "
            f"province '{own_provinces[0]}'), move existing units between your own "
            "provinces, and/or request a secret meeting with one other kingdom by id. "
            "You may also declare an attack on another kingdom if you're prepared to."
        )
        schema = (
            '{"tax_rate": 0.0-1.0, "research": "tech_id or null", '
            '"build_units": {"unit_type": count, ...}, '
            '"move_units": {"from": "province_id", "to": "province_id", "unit_type": "string", "count": int} or null, '
            '"secret_meeting_request": "kingdom_id or null", '
            '"declare_war_on": "kingdom_id or null", '
            '"reasoning": "short private reasoning, 1-2 sentences"}'
        )
        decision = agents[kid].decide(prompt, schema)
        planned_actions[kid] = decision

        if decision.get("secret_meeting_request"):
            secret_requests[kid] = [decision["secret_meeting_request"]]

    # 3. Public conference
    log_lines.append("\n## Conference (Public)\n")
    transcript = run_conference(game_state, agents)
    for msg in transcript:
        log_lines.append(f"- **{msg['name']}**: {msg['message']}")

    # 4. Secret meetings
    log_lines.append("\n## Secret Meetings\n")
    secret_log = run_secret_meetings(game_state, agents, secret_requests)
    if not secret_log:
        log_lines.append("_(none this turn)_")
    for pair_key, exchange in secret_log.items():
        ids = pair_key.split("|")
        names = [game_state.kingdoms[i].name for i in ids]
        log_lines.append(f"\n**Secret meeting: {names[0]} <-> {names[1]}** (hidden from others)")
        for msg in exchange:
            speaker_name = game_state.kingdoms[msg["from"]].name
            log_lines.append(f"  - {speaker_name}: {msg['message']}")

    # 5. Resolve actions -- engine validates everything, AI decisions are proposals only
    log_lines.append("\n## Resolution\n")
    for kid, decision in planned_actions.items():
        kingdom = game_state.kingdoms[kid]
        applied = []

        # tax rate
        if "tax_rate" in decision:
            try:
                kingdom.tax_rate = max(0.10, min(0.45, float(decision["tax_rate"])))
                applied.append(f"tax rate set to {kingdom.tax_rate:.2f}")
            except (TypeError, ValueError):
                pass

        # research
        tech_choice = decision.get("research")
        if tech_choice and not kingdom.researching and can_research(tech_choice, kingdom.unlocked_tech):
            kingdom.researching = tech_choice
            kingdom.research_progress = 0
            applied.append(f"started researching {tech_choice}")

        # unit builds -- validated against treasury and tech, one unit type at a time,
        # rejecting/partial-filling anything unaffordable rather than trusting the AI's math
        build_requests = decision.get("build_units") or {}
        capital = capital_province(kingdom.home_continent)
        for unit_type, count in build_requests.items():
            if unit_type not in UNIT_TYPES or not can_build_unit(unit_type, kingdom.unlocked_tech):
                continue
            try:
                count = int(count)
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            unit_cost = UNIT_TYPES[unit_type]["cost"]
            affordable_count = min(count, int(kingdom.treasury // unit_cost))
            if affordable_count > 0:
                kingdom.treasury -= affordable_count * unit_cost
                kingdom.units[unit_type] = kingdom.units.get(unit_type, 0) + affordable_count
                kingdom.unit_positions.setdefault(capital, {})
                kingdom.unit_positions[capital][unit_type] = (
                    kingdom.unit_positions[capital].get(unit_type, 0) + affordable_count
                )
                applied.append(f"built {affordable_count}x {unit_type} at {capital}")
            if affordable_count < count:
                applied.append(f"(could not afford {count - affordable_count}x {unit_type})")

        # troop movement between own provinces -- validated so units can't
        # teleport from a province they don't actually have forces in
        move = decision.get("move_units")
        if move and isinstance(move, dict):
            own_provinces = set(continent_province_ids(kingdom.home_continent))
            src, dst, unit_type = move.get("from"), move.get("to"), move.get("unit_type")
            try:
                move_count = int(move.get("count", 0))
            except (TypeError, ValueError):
                move_count = 0
            if (
                src in own_provinces and dst in own_provinces and unit_type in UNIT_TYPES
                and move_count > 0
                and kingdom.unit_positions.get(src, {}).get(unit_type, 0) >= move_count
            ):
                kingdom.unit_positions[src][unit_type] -= move_count
                kingdom.unit_positions.setdefault(dst, {})
                kingdom.unit_positions[dst][unit_type] = (
                    kingdom.unit_positions[dst].get(unit_type, 0) + move_count
                )
                applied.append(f"moved {move_count}x {unit_type} from {src} to {dst}")

        # war declarations
        target = decision.get("declare_war_on")
        if target and target in game_state.kingdoms and target != kid:
            if target not in kingdom.at_war_with:
                kingdom.at_war_with.append(target)
                game_state.kingdoms[target].at_war_with.append(kid)
                applied.append(f"declared WAR on {game_state.kingdoms[target].name}")

        log_lines.append(f"- **{kingdom.name}**: " + (", ".join(applied) if applied else "no action"))

    # 6. Combat resolution for any active wars (simple: if at war, a skirmish happens this turn)
    log_lines.append("\n## Combat\n")
    resolved_pairs = set()
    for kid, kingdom in game_state.kingdoms.items():
        for enemy_id in kingdom.at_war_with:
            pair_key = "|".join(sorted([kid, enemy_id]))
            if pair_key in resolved_pairs:
                continue
            resolved_pairs.add(pair_key)
            enemy = game_state.kingdoms[enemy_id]
            result = resolve_combat(kingdom.units, enemy.units)
            if result["outcome"] == "no_combat":
                continue
            for u, lost in result["attacker_losses"].items():
                kingdom.units[u] = max(0, kingdom.units.get(u, 0) - lost)
            for u, lost in result["defender_losses"].items():
                enemy.units[u] = max(0, enemy.units.get(u, 0) - lost)
            log_lines.append(
                f"- **{kingdom.name} vs {enemy.name}**: {result['outcome']} "
                f"(atk power {result['attacker_power']}, def power {result['defender_power']}) -- "
                f"{kingdom.name} lost {result['attacker_losses']}, {enemy.name} lost {result['defender_losses']}"
            )

    log_text = "\n".join(log_lines)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / f"turn_{game_state.turn}.md"
    log_path.write_text(log_text, encoding="utf-8")

    game_state.history.append({"turn": game_state.turn, "summary": log_text[:2000]})

    # God-view map: regenerated every turn so you can watch troop positions,
    # ownership, and terrain evolve turn over turn.
    from src.map_render import render_map_html
    map_dir = Path(log_dir).parent / "maps" if Path(log_dir).name == "logs" else Path("maps")
    map_dir.mkdir(parents=True, exist_ok=True)
    map_html = render_map_html(game_state)
    (map_dir / f"turn_{game_state.turn}.html").write_text(map_html, encoding="utf-8")
    (map_dir / "latest.html").write_text(map_html, encoding="utf-8")  # always overwritten -- open this one to watch live

    return log_text

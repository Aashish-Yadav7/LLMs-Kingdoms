"""
The turn loop. This is the referee: it runs the economy automatically,
lets each kingdom's LLM plan and negotiate, then validates and applies
every submitted action against the real game rules. No AI output is ever
trusted blindly -- everything with a cost is checked against treasury/tech.
"""

from pathlib import Path

from src.economy import (
    run_economy_tick, research_tick, apply_repair_investment,
    run_discovery_tick, apply_colonial_tribute,
)
from src.military import UNIT_TYPES, can_build_unit, resolve_combat, apply_post_combat_morale
from src.tech_tree import TECH_TREE, can_research, get_available_techs
from src.diplomacy import run_conference, run_secret_meetings
from src.agents.llm_agent import LLMAgent
from src.map import (
    capital_province, continent_province_ids,
    provinces_adjacent, province_borders, is_island,
)


def build_agents(game_state) -> dict:
    agents = {}
    for kid, kingdom in game_state.kingdoms.items():
        agents[kid] = LLMAgent(kingdom.model, kingdom.name, kingdom.personality)
    return agents


def run_turn(game_state, agents: dict, log_dir: str = "logs") -> str:
    game_state.turn += 1
    log_lines = [f"# Turn {game_state.turn}\n"]

    provinces_per_kingdom = {
        kid: len(continent_province_ids(k.home_continent))
        for kid, k in game_state.kingdoms.items()
    }

    # 1. Economy tick (automatic, no AI involved) + discovery + colonial tribute
    log_lines.append("## Economy\n")
    for kid, kingdom in game_state.kingdoms.items():
        summary = run_economy_tick(kingdom)
        research_summary = research_tick(kingdom)
        log_lines.append(
            f"- **{kingdom.name}**: treasury ${summary['treasury_after']:,.0f}, "
            f"pop {summary['population_after']:,}, "
            f"tax income ${summary['tax_income']:,.0f}, "
            f"upkeep ${summary['upkeep_cost']:,.0f}, "
            f"stability {summary['stability_after']}/100, "
            f"morale {kingdom.morale:.0f}/150"
            + (" -- FOOD SHORTAGE" if summary["starving"] else "")
        )
        if research_summary["status"] == "completed":
            log_lines.append(f"  - Research complete: **{research_summary['tech']}**")
        if summary["riot"]:
            r = summary["riot"]
            log_lines.append(
                f"  - **RIOT** (tax rate too high for too long): lost {r['population_lost']:,} population, "
                f"${r['treasury_damage']:,.0f} in property/infrastructure damage, "
                f"units lost: {r['units_lost'] or 'none'}"
            )

        # Discovery -- isolated kingdoms only start finding others once
        # basic_navigation is unlocked, and even then it's gradual, not instant.
        newly_discovered = run_discovery_tick(kingdom, list(game_state.kingdoms.keys()))
        if newly_discovered:
            names = [game_state.kingdoms[k].name for k in newly_discovered]
            log_lines.append(f"  - **Discovery**: made first contact with {', '.join(names)}")

        # Colonial tribute -- any provinces this kingdom colonizes elsewhere
        # extract a cut of that province's economy every turn, automatically.
        for prov_id, colony_info in list(kingdom.colonies.items()):
            original_owner = game_state.kingdoms.get(colony_info.get("from_kingdom"))
            if not original_owner:
                continue
            tribute = apply_colonial_tribute(kingdom, original_owner, prov_id, provinces_per_kingdom)
            log_lines.append(
                f"  - Colonial tribute from {prov_id} ({original_owner.name}): +${tribute:,.0f}"
            )

    # 2. Private planning: each kingdom decides its economic/military/research
    #    action, plus who (if anyone) it wants a secret meeting with.
    log_lines.append("\n## Private Decisions\n")
    secret_requests = {}
    planned_actions = {}
    for kid, kingdom in game_state.kingdoms.items():
        # Only show intel on kingdoms this one has actually discovered --
        # true fog of war, not just "hidden until you unlock navigation".
        others = [
            k.intel_view(kid) for oid, k in game_state.kingdoms.items()
            if oid != kid and oid in kingdom.known_kingdoms
        ]
        available_techs = get_available_techs(kingdom.unlocked_tech)
        buildable_units = [u for u in UNIT_TYPES if can_build_unit(u, kingdom.unlocked_tech)]
        own_provinces = continent_province_ids(kingdom.home_continent)
        frontier = {
            prov: province_borders(prov) for prov in own_provinces
            if any(game_state.province_owners.get(b) != kingdom.id for b in province_borders(prov))
        }

        navigation_note = (
            "You have NOT researched basic_navigation yet -- your kingdom doesn't "
            "know any other kingdom exists. You cannot speak in conference or "
            "request secret meetings until you research it.\n\n"
            if "basic_navigation" not in kingdom.unlocked_tech else
            f"Kingdoms you have discovered so far: {sorted(kingdom.known_kingdoms) or '(none yet)'}\n\n"
        )

        prompt = (
            f"Turn {game_state.turn}. Your private state:\n{kingdom.private_summary()}\n\n"
            f"Your current stability: {kingdom.stability}/100. Tax rates above 30% erode stability "
            "over time; if it collapses you WILL get a riot (population loss, treasury damage, "
            "military losses). You can spend money via 'repair_investment' to actively restore "
            "stability instead of waiting.\n\n"
            f"Your current morale: {kingdom.morale:.0f}/150 -- this drives your actual combat "
            "power as much as unit count does. A smaller force at high morale can beat a larger "
            "one at low morale. Morale rises with victories and high stability, falls with "
            "defeats and prolonged wars.\n\n"
            f"{navigation_note}"
            f"Other kingdoms you know about (info available to you):\n{others}\n\n"
            f"Techs you could start researching now: {available_techs}\n"
            f"Unit types you can currently build: {buildable_units}\n"
            f"Unit costs/upkeep reference: { {u: {'cost': d['cost'], 'upkeep': d['upkeep']} for u, d in UNIT_TYPES.items()} }\n"
            f"Your provinces (for troop movement): {own_provinces}\n"
            f"Current unit deployment by province: {kingdom.unit_positions}\n"
            f"Your frontier provinces and what borders them beyond your own territory "
            f"(the only places a single move can reach outside your kingdom): {frontier}\n"
            f"Your custom project in progress: {kingdom.custom_researching or 'none'}\n"
            f"Your completed custom projects: {[p['name'] for p in kingdom.custom_projects]}\n"
            f"Provinces you currently colonize (belonging to other kingdoms): {list(kingdom.colonies.keys()) or 'none'}\n\n"
            "Decide this turn's action. You may set your tax rate (0.10-0.45), "
            "start researching one tech (or continue current research), "
            "build units (limited by treasury; new units appear at your capital "
            f"province '{own_provinces[0]}'), invest money to repair stability, propose "
            "your OWN custom project (a named invention with a cost and turn count you "
            "set -- must cost at least $500B and take 1-15 turns, engine will validate "
            "affordability), and/or request a secret meeting with one KNOWN kingdom by id.\n\n"
            "Movement/attack: 'move_units' moves one unit type between two DIRECTLY "
            "ADJACENT provinces only (see the frontier map above and each other kingdom's "
            "province borders) -- no teleporting across the map in one turn. Moving into "
            "your own province is peaceful repositioning. Moving into a province belonging "
            "to a kingdom you are at war with is an ATTACK: if enemy units are stationed "
            "there, combat resolves this turn using only the forces actually present in "
            "that province, not your whole army. You may also move onto an unclaimed "
            "island adjacent to your territory to explore/claim it. You may declare war on "
            "another KNOWN kingdom this turn (declare_war_on) -- you cannot attack their "
            "territory until you are at war with them, and you cannot even know they exist "
            "until you've discovered them.\n\n"
            "Colonization: if you have units occupying a foreign province (belonging to "
            "another kingdom) with NO defending forces present, you may set "
            "'colonize_province' to that province id to bring it under your economic "
            "control -- you'll extract ongoing tribute from it each turn. This does not "
            "require you to be at war (an undefended province can simply be occupied)."
        )
        schema = (
            '{"tax_rate": 0.0-1.0, "research": "tech_id or null", '
            '"build_units": {"unit_type": count, ...}, '
            '"move_units": {"from": "province_id", "to": "adjacent province_id (own territory, enemy territory if at war, or an adjacent unclaimed island)", '
            '"unit_type": "string", "count": int} or null, '
            '"repair_investment": number or null, '
            '"custom_project": {"name": "string", "description": "string", "category": "string", '
            '"proposed_cost": number, "proposed_turns": int} or null, '
            '"colonize_province": "province_id or null", '
            '"secret_meeting_request": "kingdom_id or null", '
            '"declare_war_on": "kingdom_id or null", '
            '"reasoning": "short private reasoning, 1-2 sentences"}'
        )
        decision = agents[kid].decide(prompt, schema)
        planned_actions[kid] = decision

        reasoning = decision.get("reasoning")
        log_lines.append(f"- **{kingdom.name}**: {reasoning if reasoning else '_(no reasoning given)_'}")
        game_state.turn_reasoning[kid] = reasoning or "(no reasoning given)"

        if decision.get("secret_meeting_request"):
            secret_requests[kid] = [decision["secret_meeting_request"]]

    # 3. Public conference
    log_lines.append("\n## Conference (Public)\n")
    transcript = run_conference(game_state, agents)
    if not transcript:
        log_lines.append("_(no public messages this turn -- either no kingdom has discovered "
                          "navigation yet, or nobody had anything to say)_")
    for msg in transcript:
        voice_tag = "*(narrator)*" if msg.get("voice") == "narrator" else ""
        log_lines.append(f"- **{msg['name']}** {voice_tag}: {msg['message']}")

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
            tech_cost = TECH_TREE[tech_choice]["cost"]
            if kingdom.treasury >= tech_cost:
                kingdom.treasury -= tech_cost
                kingdom.researching = tech_choice
                kingdom.research_progress = 0
                applied.append(f"started researching {tech_choice} (-${tech_cost:,.0f})")
            else:
                applied.append(f"(wanted to research {tech_choice} but couldn't afford ${tech_cost:,.0f})")

        # unit builds
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

        # troop movement -- ownership now read from game_state.province_owners
        # (mutable, can change via colonization) rather than the static
        # map.json value.
        move = decision.get("move_units")
        if move and isinstance(move, dict):
            src, dst, unit_type = move.get("from"), move.get("to"), move.get("unit_type")
            try:
                move_count = int(move.get("count", 0))
            except (TypeError, ValueError):
                move_count = 0

            has_forces = kingdom.unit_positions.get(src, {}).get(unit_type, 0) >= move_count
            adjacent = isinstance(src, str) and isinstance(dst, str) and provinces_adjacent(src, dst)
            dst_owner = game_state.province_owners.get(dst) if isinstance(dst, str) else None
            move_allowed = (
                dst_owner == kingdom.id
                or dst_owner is None
                or dst_owner in kingdom.at_war_with
            )

            if (
                unit_type in UNIT_TYPES and move_count > 0
                and has_forces and adjacent and move_allowed
            ):
                kingdom.unit_positions[src][unit_type] -= move_count
                kingdom.unit_positions.setdefault(dst, {})
                kingdom.unit_positions[dst][unit_type] = (
                    kingdom.unit_positions[dst].get(unit_type, 0) + move_count
                )
                verb = "attacked into" if dst_owner in kingdom.at_war_with else "moved into"
                applied.append(f"{verb} {dst} with {move_count}x {unit_type} (from {src})")

                if dst_owner is None and is_island(dst):
                    island = game_state.unclaimed_islands.get(dst)
                    others_present = any(
                        oid != kid and other.unit_positions.get(dst, {})
                        for oid, other in game_state.kingdoms.items()
                    )
                    if island and island.get("controlled_by") is None and not others_present:
                        island["controlled_by"] = kid
                        game_state.province_owners[dst] = kid
                        applied.append(f"claimed unclaimed island {dst}")
            elif not move_allowed:
                applied.append(f"(cannot move into {dst} -- not at war with {dst_owner})")
            elif not adjacent:
                applied.append(f"(move rejected: {dst} does not border {src})")
            elif not has_forces:
                applied.append(f"(move rejected: no {unit_type} stationed at {src})")

        # colonization -- requires units physically present in a foreign
        # province with NO defending forces from that province's actual
        # current owner. Ownership then transfers, and ongoing tribute
        # starts flowing (see economy.apply_colonial_tribute, step 1 above).
        colonize_target = decision.get("colonize_province")
        if colonize_target and isinstance(colonize_target, str):
            target_owner = game_state.province_owners.get(colonize_target)
            attacker_present = kingdom.unit_positions.get(colonize_target, {})
            attacker_has_forces = any(c > 0 for c in attacker_present.values())
            defender_kingdom = game_state.kingdoms.get(target_owner) if target_owner else None
            defender_has_forces = bool(defender_kingdom and any(
                c > 0 for c in defender_kingdom.unit_positions.get(colonize_target, {}).values()
            ))

            if (
                target_owner and target_owner != kid and attacker_has_forces and not defender_has_forces
            ):
                game_state.province_owners[colonize_target] = kid
                kingdom.colonies[colonize_target] = {
                    "colonizer": kid, "since_turn": game_state.turn, "from_kingdom": target_owner,
                }
                applied.append(f"began colonizing {colonize_target} (formerly {defender_kingdom.name if defender_kingdom else target_owner})")
            elif colonize_target:
                applied.append(f"(colonization of {colonize_target} rejected -- either not foreign territory, no forces present, or still defended)")

        # repair investment
        repair_amount = decision.get("repair_investment")
        if repair_amount:
            try:
                repair_amount = float(repair_amount)
            except (TypeError, ValueError):
                repair_amount = 0
            if repair_amount > 0:
                result = apply_repair_investment(kingdom, repair_amount)
                if result["spent"] > 0:
                    applied.append(
                        f"invested ${result['spent']:,.0f} in stability "
                        f"(+{result['stability_gained']} stability)"
                    )

        # custom/fictional project proposal
        custom = decision.get("custom_project")
        if custom and isinstance(custom, dict) and not kingdom.custom_researching:
            name = str(custom.get("name", "")).strip()[:80]
            description = str(custom.get("description", "")).strip()[:300]
            category = str(custom.get("category", "military")).strip()[:30]
            try:
                proposed_cost = float(custom.get("proposed_cost", 0))
                proposed_turns = int(custom.get("proposed_turns", 1))
            except (TypeError, ValueError):
                proposed_cost, proposed_turns = 0, 0

            MIN_CUSTOM_PROJECT_COST = 500_000_000_000
            MAX_CUSTOM_PROJECT_TURNS = 15

            if (
                name and MIN_CUSTOM_PROJECT_COST <= proposed_cost <= kingdom.treasury
                and 1 <= proposed_turns <= MAX_CUSTOM_PROJECT_TURNS
            ):
                kingdom.treasury -= proposed_cost
                kingdom.custom_researching = {
                    "name": name,
                    "description": description,
                    "category": category,
                    "cost": proposed_cost,
                    "turns_needed": proposed_turns,
                    "progress": 0,
                }
                applied.append(f"began custom project '{name}' (-${proposed_cost:,.0f}, {proposed_turns} turns)")
            elif name:
                applied.append(f"(custom project '{name}' rejected -- cost/turns out of bounds or unaffordable)")

        if kingdom.custom_researching:
            kingdom.custom_researching["progress"] += kingdom.research_speed_multiplier
            if kingdom.custom_researching["progress"] >= kingdom.custom_researching["turns_needed"]:
                finished = kingdom.custom_researching
                finished["power_rating"] = round(finished["cost"] / 200_000_000, 1)
                kingdom.custom_projects.append(finished)
                kingdom.custom_researching = None
                applied.append(f"completed custom project '{finished['name']}'")

        # war declarations -- only possible against a KNOWN kingdom
        target = decision.get("declare_war_on")
        if target and target in game_state.kingdoms and target != kid and target in kingdom.known_kingdoms:
            if target not in kingdom.at_war_with:
                kingdom.at_war_with.append(target)
                game_state.kingdoms[target].at_war_with.append(kid)
                applied.append(f"declared WAR on {game_state.kingdoms[target].name}")

        log_lines.append(f"- **{kingdom.name}**: " + (", ".join(applied) if applied else "no action"))

    # 6. Combat resolution -- fought province by province from actual troop
    # positions, factoring in morale on top of raw unit power (see
    # military.resolve_combat). Ownership for the home-turf terrain bonus is
    # read from game_state.province_owners (mutable), not the static map.
    log_lines.append("\n## Combat\n")

    province_presence: dict[str, dict[str, dict]] = {}
    for kid, kingdom in game_state.kingdoms.items():
        for prov_id, units in kingdom.unit_positions.items():
            live = {u: c for u, c in units.items() if c > 0}
            if live:
                province_presence.setdefault(prov_id, {})[kid] = live

    any_combat = False
    for prov_id, presence in province_presence.items():
        occupants = list(presence.keys())
        for i in range(len(occupants)):
            for j in range(i + 1, len(occupants)):
                k1, k2 = occupants[i], occupants[j]
                if k2 not in game_state.kingdoms[k1].at_war_with:
                    continue

                owner = game_state.province_owners.get(prov_id)
                if owner == k1:
                    attacker_id, defender_id = k2, k1
                elif owner == k2:
                    attacker_id, defender_id = k1, k2
                else:
                    attacker_id, defender_id = sorted([k1, k2])
                attacker, defender = game_state.kingdoms[attacker_id], game_state.kingdoms[defender_id]
                terrain_bonus = 1.15 if owner == defender_id else 1.0

                result = resolve_combat(
                    presence[attacker_id], presence[defender_id],
                    attacker_morale=attacker.morale, defender_morale=defender.morale,
                    defender_terrain_bonus=terrain_bonus,
                )
                if result["outcome"] == "no_combat":
                    continue
                any_combat = True

                for u, lost in result["attacker_losses"].items():
                    attacker.unit_positions[prov_id][u] = max(0, attacker.unit_positions[prov_id].get(u, 0) - lost)
                    attacker.units[u] = max(0, attacker.units.get(u, 0) - lost)
                for u, lost in result["defender_losses"].items():
                    defender.unit_positions[prov_id][u] = max(0, defender.unit_positions[prov_id].get(u, 0) - lost)
                    defender.units[u] = max(0, defender.units.get(u, 0) - lost)

                winner, loser = (attacker, defender) if result["outcome"] == "attacker_wins" else (defender, attacker)
                apply_post_combat_morale(winner, loser)

                log_lines.append(
                    f"- **{prov_id}**: {attacker.name} (attacking, morale {attacker.morale:.0f}) vs "
                    f"{defender.name} (defending, morale {defender.morale:.0f}) -- "
                    f"{result['outcome']} (atk power {result['attacker_power']}, def power {result['defender_power']}) -- "
                    f"{attacker.name} lost {result['attacker_losses'] or 'nothing'}, "
                    f"{defender.name} lost {result['defender_losses'] or 'nothing'}"
                )
    if not any_combat:
        log_lines.append("_(no opposing forces shared a province this turn)_")

    log_text = "\n".join(log_lines)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / f"turn_{game_state.turn}.md"
    log_path.write_text(log_text, encoding="utf-8")

    game_state.history.append({"turn": game_state.turn, "summary": log_text[:2000]})

    from src.map_render import save_turn_snapshot, load_all_snapshots, render_game_html
    map_dir = Path(log_dir).parent / "maps" if Path(log_dir).name == "logs" else Path("maps")
    map_dir.mkdir(parents=True, exist_ok=True)
    save_turn_snapshot(game_state, out_dir=map_dir / "turn_data")
    all_snapshots = load_all_snapshots(snapshot_dir=map_dir / "turn_data")
    game_html = render_game_html(all_snapshots)
    (map_dir / "game.html").write_text(game_html, encoding="utf-8")

    return log_text

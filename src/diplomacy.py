"""
Handles the public conference (IFS) phase and private bilateral contact.
IFS forms only once every kingdom has discovered every other kingdom AND
all have voted for it -- see check_ifs_formation. Before that, diplomacy is
strictly bilateral via run_secret_meetings.

Every message is first person only, and grounded in the kingdom's real
resource inventory (with real-world units attached) -- never an invented
currency or resource.
"""

from src.config import MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN

RESOURCE_UNITS = {
    "oil": "barrels", "natural_gas": "barrels",
    "coal": "metric tons", "iron": "metric tons", "copper": "metric tons",
    "aluminum": "metric tons", "zinc": "metric tons", "nickel": "metric tons",
    "cobalt": "metric tons", "titanium": "metric tons", "gold": "metric tons",
    "silver": "metric tons", "platinum": "metric tons", "lithium": "metric tons",
    "rare_earth_elements": "metric tons", "uranium": "metric tons",
    "plutonium": "metric tons", "timber": "cubic meters",
    "fresh_water": "megaliters", "arable_land": "hectares",
}


def format_resources(resources: dict) -> str:
    if not resources:
        return "(no resources on record)"
    parts = [f"{name.replace('_', ' ')}: {qty:,} {RESOURCE_UNITS.get(name, 'units')}" for name, qty in resources.items()]
    return ", ".join(parts)


def _voice_instruction(kingdom_name: str) -> str:
    return (
        f"Speak as an actual government representative -- first person only "
        f"('we', 'our', 'us'). Your kingdom's name is {kingdom_name}. Do NOT "
        f"write the word '{kingdom_name}' anywhere in your own message -- "
        f"referring to yourself by your own name mid-sentence is a third-person "
        f"slip and is wrong (e.g. never say \"only if {kingdom_name} agrees\", "
        f"say \"only if we agree\" instead). You may name OTHER kingdoms by "
        f"their real names, just never your own.\n"
        "Only offer or request resources that actually appear in your resource "
        "inventory below, using their real names and quantities. Never invent "
        "a currency or resource (like 'gold coins' or generic 'gold') that "
        "isn't in that list."
    )


def check_ifs_formation(game_state, decisions: dict) -> bool:
    if game_state.ifs_formed:
        return False
    all_ids = set(game_state.kingdoms.keys())
    fully_discovered = [
        kid for kid, k in game_state.kingdoms.items()
        if k.known_kingdoms >= (all_ids - {kid})
    ]
    if len(fully_discovered) < len(all_ids):
        return False
    for kid in fully_discovered:
        if decisions.get(kid, {}).get("vote_for_ifs"):
            game_state.ifs_votes.add(kid)
    if game_state.ifs_votes >= all_ids:
        game_state.ifs_formed = True
        return True
    return False


def run_conference(game_state, agents: dict) -> list:
    if not game_state.ifs_formed:
        game_state.conference_log = []
        return []
    transcript = []
    for kid, kingdom in game_state.kingdoms.items():
        others = [k.public_summary() for oid, k in game_state.kingdoms.items() if oid != kid]
        for _ in range(MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN):
            prompt = (
                f"Turn {game_state.turn}. This is a session of the International "
                "Federation of States (IFS) -- every member kingdom sees what you say here.\n\n"
                f"Other member kingdoms:\n{others}\n\n"
                f"Your real resource inventory:\n{format_resources(kingdom.resources)}\n\n"
                f"Session so far this turn:\n{transcript}\n\n"
                "You may make ONE formal floor statement. Keep it to 1-2 sentences.\n"
                f"{_voice_instruction(kingdom.name)}\n"
                "If you have nothing to add, set 'speak' to false."
            )
            schema = '{"speak": true/false, "message": "string, empty if speak is false"}'
            result = agents[kid].decide(prompt, schema)
            if result.get("speak"):
                transcript.append({"from": kid, "name": kingdom.name, "message": result.get("message", "")})
    game_state.conference_log = transcript
    return transcript


def run_secret_meetings(game_state, agents: dict, requests: dict) -> dict:
    log = {}
    seen_pairs = set()
    for kid, targets in requests.items():
        requester = game_state.kingdoms.get(kid)
        if not requester:
            continue
        for target in targets:
            if target not in game_state.kingdoms or target not in requester.known_kingdoms:
                continue
            pair_key = "|".join(sorted([kid, target]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            accept_result = agents[target].decide(
                f"{game_state.kingdoms[kid].name} has requested a private meeting with you. "
                "Only the two of you will see this conversation. Do you accept?",
                '{"accept": true/false}'
            )
            if not accept_result.get("accept"):
                continue

            exchange = []
            for round_ in range(2):
                for speaker in [kid, target]:
                    other = target if speaker == kid else kid
                    speaker_kingdom = game_state.kingdoms[speaker]
                    prompt = (
                        f"Private meeting with {game_state.kingdoms[other].name}. Nobody else "
                        "will ever see this unless one of you reveals it later.\n"
                        f"Your real resource inventory:\n{format_resources(speaker_kingdom.resources)}\n\n"
                        f"Conversation so far:\n{exchange}\n\n"
                        "Propose an alliance, plan a joint action, negotiate a trade, or share "
                        "intel. 1-3 sentences.\n"
                        f"{_voice_instruction(speaker_kingdom.name)}"
                    )
                    result = agents[speaker].decide(prompt, '{"message": "string"}')
                    exchange.append({"from": speaker, "message": result.get("message", "")})
            log[pair_key] = exchange
    game_state.secret_meeting_log = log
    return log

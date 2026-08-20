"""
Handles the public conference phase and private secret-meeting phase.
Public messages are visible to all kingdoms next turn's context; secret
messages are only ever shown to the two participants -- other kingdoms never
see they happened unless a participant later reveals it (an in-character
choice, not something the engine forces).
"""

from src.config import MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN


def run_conference(game_state, agents: dict) -> list:
    """
    Each kingdom gets up to N public messages this turn. Everyone sees the
    whole transcript as it forms (later speakers see earlier messages this
    same conference).
    """
    transcript = []
    for kid, kingdom in game_state.kingdoms.items():
        for _ in range(MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN):
            others = [k.public_summary() for oid, k in game_state.kingdoms.items() if oid != kid]
            prompt = (
                f"Turn {game_state.turn}. This is the public conference -- every kingdom "
                "sees what you say here.\n\n"
                f"Other kingdoms (public info only):\n{others}\n\n"
                f"Conference so far this turn:\n{transcript}\n\n"
                "You may send ONE public message (propose an alliance, make a threat, "
                "announce a trade offer, or say nothing meaningful). Keep it to 1-3 sentences. "
                "If you have nothing to add, set 'speak' to false."
            )
            schema = '{"speak": true/false, "message": "string, empty if speak is false"}'
            result = agents[kid].decide(prompt, schema)
            if result.get("speak"):
                transcript.append({"from": kid, "name": kingdom.name, "message": result.get("message", "")})
    game_state.conference_log = transcript
    return transcript


def run_secret_meetings(game_state, agents: dict, requests: dict) -> dict:
    """
    requests: {kingdom_id: [target_kingdom_id, ...]} -- who wants to talk to whom,
    gathered during private planning. A meeting only happens if BOTH sides are
    willing (target must also agree when asked).
    Returns secret_meeting_log: {"kidA|kidB": [messages]}
    """
    log = {}
    seen_pairs = set()

    for kid, targets in requests.items():
        for target in targets:
            pair_key = "|".join(sorted([kid, target]))
            if pair_key in seen_pairs or target not in game_state.kingdoms:
                continue
            seen_pairs.add(pair_key)

            # Ask the target if they accept the secret meeting
            accept_prompt = (
                f"{game_state.kingdoms[kid].name} has requested a secret, private meeting "
                "with you. Only the two of you will see this conversation. Do you accept?"
            )
            accept_schema = '{"accept": true/false}'
            accept_result = agents[target].decide(accept_prompt, accept_schema)
            if not accept_result.get("accept"):
                continue

            # Run a short private exchange (2 messages each side)
            exchange = []
            participants = [kid, target]
            for round_ in range(2):
                for speaker in participants:
                    other = target if speaker == kid else kid
                    prompt = (
                        f"SECRET meeting with {game_state.kingdoms[other].name}. "
                        "Nobody else will ever see this unless one of you reveals it later.\n"
                        f"Conversation so far:\n{exchange}\n\n"
                        "Say what you want to (propose an alliance, plan a joint attack, "
                        "negotiate a trade, or share intel). 1-3 sentences."
                    )
                    schema = '{"message": "string"}'
                    result = agents[speaker].decide(prompt, schema)
                    exchange.append({"from": speaker, "message": result.get("message", "")})

            log[pair_key] = exchange

    game_state.secret_meeting_log = log
    return log

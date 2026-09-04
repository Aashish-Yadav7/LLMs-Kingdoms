"""
Handles the public conference phase and private secret-meeting phase.
Public messages are visible to all kingdoms next turn's context; secret
messages are only ever shown to the two participants -- other kingdoms never
see they happened unless a participant later reveals it (an in-character
choice, not something the engine forces).

DISCOVERY GATING: a kingdom that hasn't unlocked "basic_navigation" doesn't
attend the conference at all -- it's still isolated, unaware anyone else
exists. A kingdom that HAS unlocked navigation attends, but only ever sees
intel on kingdoms it has personally discovered (kingdom.known_kingdoms) --
being in the same room doesn't mean you recognize everyone in it yet. Secret
meeting requests are similarly restricted to known kingdoms only -- you
can't conspire with someone you don't know exists.

TWO-MESSAGE STRUCTURE: each kingdom gets exactly 2 conference turns per
round. The first is narrator-style third person (a storyteller describing
what the kingdom is doing/deciding), the second is first-person in-character
dialogue (the ruler actually speaking). This gives every kingdom's turn a
consistent "scene" shape -- narration, then voice -- rather than one
inconsistent style throughout.
"""

from src.config import MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN


def run_conference(game_state, agents: dict) -> list:
    """
    Each kingdom that has discovered navigation gets up to N public messages
    this turn. Everyone attending sees the whole transcript as it forms
    (later speakers see earlier messages this same conference), but each
    kingdom's own view of "who else is here" is filtered to who they've
    personally discovered.
    """
    transcript = []
    attendees = {
        kid: kingdom for kid, kingdom in game_state.kingdoms.items()
        if "basic_navigation" in kingdom.unlocked_tech
    }

    for kid, kingdom in attendees.items():
        known_attendees = [
            k.public_summary() for oid, k in attendees.items()
            if oid != kid and oid in kingdom.known_kingdoms
        ]
        for msg_index in range(MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN):
            if msg_index == 0:
                voice_instruction = (
                    "This first message should be told like a NARRATOR describing "
                    "the scene from outside -- third person, like a storyteller "
                    "setting up what this kingdom is doing or deciding right now "
                    "('The North, its granaries thinning, turns its gaze south...'). "
                    "Do not use 'I' or 'we' in this one."
                )
            else:
                voice_instruction = (
                    "This second message is the ruler actually SPEAKING -- first "
                    "person ('I' or 'we'), direct dialogue, as if addressing the "
                    "room. Never narrate about your own kingdom in the third "
                    "person here."
                )

            prompt = (
                f"Turn {game_state.turn}. This is the public conference -- every kingdom "
                "present sees what you say here.\n\n"
                f"Kingdoms you have discovered and can address here:\n{known_attendees}\n\n"
                f"Conference so far this turn:\n{transcript}\n\n"
                "You may send ONE public message (propose an alliance, make a threat, "
                "announce a trade offer, or say nothing meaningful). Keep it to 1-2 sentences. "
                f"{voice_instruction} "
                "If you have nothing to add, set 'speak' to false."
            )
            schema = '{"speak": true/false, "message": "string, empty if speak is false"}'
            result = agents[kid].decide(prompt, schema)
            if result.get("speak"):
                transcript.append({
                    "from": kid, "name": kingdom.name, "message": result.get("message", ""),
                    "voice": "narrator" if msg_index == 0 else "dialogue",
                })
    game_state.conference_log = transcript
    return transcript


def run_secret_meetings(game_state, agents: dict, requests: dict) -> dict:
    """
    requests: {kingdom_id: [target_kingdom_id, ...]} -- who wants to talk to whom,
    gathered during private planning. A meeting only happens if BOTH sides are
    willing (target must also agree when asked) AND the requester has actually
    discovered the target -- you cannot secretly conspire with a kingdom whose
    existence you don't even know about yet.
    Returns secret_meeting_log: {"kidA|kidB": [messages]}
    """
    log = {}
    seen_pairs = set()

    for kid, targets in requests.items():
        requester = game_state.kingdoms.get(kid)
        if not requester or "basic_navigation" not in requester.unlocked_tech:
            continue
        for target in targets:
            if target not in game_state.kingdoms or target not in requester.known_kingdoms:
                continue
            pair_key = "|".join(sorted([kid, target]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            accept_prompt = (
                f"{game_state.kingdoms[kid].name} has requested a secret, private meeting "
                "with you. Only the two of you will see this conversation. Do you accept?"
            )
            accept_schema = '{"accept": true/false}'
            accept_result = agents[target].decide(accept_prompt, accept_schema)
            if not accept_result.get("accept"):
                continue

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
                        "negotiate a trade, or share intel). 1-3 sentences. Always speak in "
                        "first person ('I' or 'we') -- never narrate about your own kingdom "
                        "in the third person."
                    )
                    schema = '{"message": "string"}'
                    result = agents[speaker].decide(prompt, schema)
                    exchange.append({"from": speaker, "message": result.get("message", "")})

            log[pair_key] = exchange

    game_state.secret_meeting_log = log
    return log

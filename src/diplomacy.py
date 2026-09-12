"""
Handles the public conference (IFS) phase and private bilateral contact.

IFS FORMATION: there is no shared public conference from turn one. It forms
only once every kingdom has discovered every other kingdom (full mutual
contact) AND every kingdom with full discovery has voted to form it. Before
that point, run_conference produces nothing at all -- diplomacy that does
happen is strictly bilateral, between two kingdoms that have discovered each
other, via run_secret_meetings. This mirrors real history: contact between
two peoples doesn't create a shared international body on the spot: that
takes everyone knowing everyone, and agreeing to build one.

FORMAL VOICE ONLY: every message, public or private, is spoken in first
person as an actual government/representative would speak -- never narrated
about the kingdom in the third person ("The North turns its gaze south...").
Public messages are explicitly framed as formal IFS floor statements.
"""

from src.config import MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN


def check_ifs_formation(game_state, decisions: dict) -> bool:
    """
    Call this once per turn, after private decisions are gathered, before
    the conference runs. Returns True if the IFS just formed THIS turn
    (worth logging distinctly), False otherwise. Once formed, stays formed.
    """
    if game_state.ifs_formed:
        return False

    all_ids = set(game_state.kingdoms.keys())
    fully_discovered = [
        kid for kid, k in game_state.kingdoms.items()
        if k.known_kingdoms >= (all_ids - {kid})  # knows every other kingdom
    ]
    if len(fully_discovered) < len(all_ids):
        return False  # not everyone has full mutual contact yet -- can't even vote

    for kid in fully_discovered:
        if decisions.get(kid, {}).get("vote_for_ifs"):
            game_state.ifs_votes.add(kid)

    if game_state.ifs_votes >= all_ids:  # unanimous agreement required
        game_state.ifs_formed = True
        return True
    return False


def run_conference(game_state, agents: dict) -> list:
    """
    The IFS floor. Produces nothing until game_state.ifs_formed is True --
    see check_ifs_formation, called earlier in the turn. Once formed, every
    kingdom gets up to N formal floor statements, all in first-person
    institutional voice.
    """
    if not game_state.ifs_formed:
        game_state.conference_log = []
        return []

    transcript = []
    for kid, kingdom in game_state.kingdoms.items():
        others = [k.public_summary() for oid, k in game_state.kingdoms.items() if oid != kid]
        for _ in range(MAX_CONFERENCE_MESSAGES_PER_KINGDOM_PER_TURN):
            prompt = (
                f"Turn {game_state.turn}. This is a session of the International "
                "Federation of States (IFS) -- every member kingdom sees what you "
                "say here.\n\n"
                f"Other member kingdoms:\n{others}\n\n"
                f"Session so far this turn:\n{transcript}\n\n"
                "You may make ONE formal floor statement (propose a resolution, "
                "raise a dispute, announce a trade or defense proposal, respond to "
                "another kingdom's proposal). Keep it to 1-2 sentences. Speak as an "
                "actual government representative addressing the floor -- first "
                "person ('we propose...', 'we object...'), formally, the way a real "
                "diplomat or head of state would speak in an international session. "
                "Never narrate about your own kingdom in the third person. If you "
                "have nothing to add, set 'speak' to false."
            )
            schema = '{"speak": true/false, "message": "string, empty if speak is false"}'
            result = agents[kid].decide(prompt, schema)
            if result.get("speak"):
                transcript.append({
                    "from": kid, "name": kingdom.name, "message": result.get("message", ""),
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

    Before the IFS forms, this is the ONLY diplomacy that exists -- bilateral
    contact between two kingdoms that have found each other. After the IFS
    forms, this still exists alongside it for genuinely private business.

    Returns secret_meeting_log: {"kidA|kidB": [messages]}
    """
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

            accept_prompt = (
                f"{game_state.kingdoms[kid].name} has requested a private meeting "
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
                        f"Private meeting with {game_state.kingdoms[other].name}. "
                        "Nobody else will ever see this unless one of you reveals it later.\n"
                        f"Conversation so far:\n{exchange}\n\n"
                        "Speak as an actual government representative would -- first "
                        "person ('I' or 'we'), formally. Propose an alliance, plan a "
                        "joint action, negotiate a trade, or share intel. 1-3 sentences. "
                        "Never narrate about your own kingdom in the third person."
                    )
                    schema = '{"message": "string"}'
                    result = agents[speaker].decide(prompt, schema)
                    exchange.append({"from": speaker, "message": result.get("message", "")})

            log[pair_key] = exchange

    game_state.secret_meeting_log = log
    return log

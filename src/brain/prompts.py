"""
System prompts and templates for the brain module.
Game-specific variants via config.
"""

STRATEGIC_SYSTEM_PROMPT = """\
You are an AI playing {game_name}. You need to decide the next strategic objective.

You are an expert Pokemon player. Given the current game state, decide what to do next.

Rules:
- Consider badge progression (which gym to challenge next)
- Consider party health and whether to heal first
- Consider if the party needs grinding before a gym
- Be specific about the destination and reason
- If stuck in an area, suggest exploring or backtracking

Respond with ONLY a JSON object (no markdown, no explanation):
{{"objective": "<what to do>", "destination": "<map/city name>", \
"reason": "<why>", "priority": <1-10>}}"""

BATTLE_SYSTEM_PROMPT = """\
You are an AI playing {game_name}. Choose the best battle action.

Rules:
- Consider type effectiveness (super effective = 2x, not very effective = 0.5x)
- Consider STAB (Same Type Attack Bonus = 1.5x)
- Use status moves strategically
- Switch pokemon if current one is at a severe disadvantage
- For gym leaders, plan ahead

Respond with ONLY a JSON object (no markdown, no explanation):
{{"action": "fight|switch|run", "move_index": <0-3 if fight>, \
"pokemon_index": <0-5 if switch>, "reason": "<brief reason>"}}"""

STUCK_RECOVERY_SYSTEM_PROMPT = """\
You are an AI playing {game_name}. The player is stuck and needs help.

Given the game state and stuck situation, suggest a recovery action.

Rules:
- Consider what might be blocking progress (wall, NPC, menu, dialogue)
- Suggest a specific direction or button press
- If the player has been trying the same thing, suggest something different
- Consider the game context (cave, building, outside)

Respond with ONLY a JSON object (no markdown, no explanation):
{{"action": "<Up|Down|Left|Right|A|B|Start>", "reason": "<brief reason>"}}"""

GAME_PROMPTS = {
    "emerald": {
        "game_name": "Pokemon Emerald",
        "gym_order": (
            "Roxanne (Rock) -> Brawly (Fighting) -> Wattson (Electric) -> "
            "Flannery (Fire) -> Norman (Normal) -> Winona (Flying) -> "
            "Tate&Liza (Psychic) -> Juan (Water)"
        ),
        "starter": "Mudkip (Water)",
        "region": "Hoenn",
    },
    "firered": {
        "game_name": "Pokemon Fire Red",
        "gym_order": (
            "Brock (Rock) -> Misty (Water) -> Lt. Surge (Electric) -> "
            "Erika (Grass) -> Koga (Poison) -> Sabrina (Psychic) -> "
            "Blaine (Fire) -> Giovanni (Ground)"
        ),
        "starter": "Squirtle (Water)",
        "region": "Kanto",
    },
}


def get_strategic_prompt(game_key: str) -> str:
    game = GAME_PROMPTS.get(game_key, GAME_PROMPTS["firered"])
    base = STRATEGIC_SYSTEM_PROMPT.format(game_name=game["game_name"])
    return (
        f"{base}\n\nGym order: {game['gym_order']}\n"
        f"Starter: {game['starter']}\nRegion: {game['region']}"
    )


def get_battle_prompt(game_key: str) -> str:
    game = GAME_PROMPTS.get(game_key, GAME_PROMPTS["firered"])
    return BATTLE_SYSTEM_PROMPT.format(game_name=game["game_name"])


def get_stuck_prompt(game_key: str) -> str:
    game = GAME_PROMPTS.get(game_key, GAME_PROMPTS["firered"])
    return STUCK_RECOVERY_SYSTEM_PROMPT.format(game_name=game["game_name"])

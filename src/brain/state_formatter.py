"""
Formats game state into compact text for LLM prompts.
"""


class StateFormatter:
    """Converts game state data into compact LLM-ready text."""

    @staticmethod
    def format_strategic_state(
        badges: int,
        current_map: tuple[int, int],
        map_name: str,
        party: list[dict],
        position: tuple[int, int],
        recent_events: list[str] = None,
        game_name: str = "Pokemon",
    ) -> str:
        party_text = []
        for i, mon in enumerate(party):
            hp_pct = (mon.get("hp", 0) / max(mon.get("max_hp", 1), 1)) * 100
            status = mon.get("status", 0)
            status_text = f" [{status}]" if status else ""
            species = mon.get("species", "?")
            party_text.append(
                f"  {i+1}. {species} Lv{mon.get('level', '?')} "
                f"HP:{hp_pct:.0f}%{status_text}"
            )

        lines = [
            f"Game: {game_name}",
            f"Badges: {badges}/8",
            f"Location: {map_name} (map {current_map[0]},{current_map[1]}) "
            f"@ ({position[0]},{position[1]})",
            f"Party ({len(party)} pokemon):",
            *party_text,
        ]

        if recent_events:
            lines.append("Recent events:")
            for event in recent_events[-5:]:
                lines.append(f"  - {event}")

        return "\n".join(lines)

    @staticmethod
    def format_battle_state(
        player_pokemon: dict,
        enemy_pokemon: dict,
        is_trainer: bool,
        weather: str = "none",
    ) -> str:
        def fmt_pokemon(p: dict, label: str) -> list[str]:
            hp_pct = (p.get("hp", 0) / max(p.get("max_hp", 1), 1)) * 100
            lines = [
                f"{label}: Lv{p.get('level', '?')} {p.get('species', '?')} "
                f"HP:{hp_pct:.0f}%",
                f"  Types: {', '.join(p.get('types', ['?']))}",
            ]
            moves = p.get("moves", [])
            if moves:
                move_strs = []
                for m in moves:
                    pp_text = (
                        f" PP:{m.get('pp', '?')}/{m.get('max_pp', '?')}"
                        if "pp" in m
                        else ""
                    )
                    move_strs.append(
                        f"{m.get('name', '?')} "
                        f"(pwr:{m.get('power', 0)} "
                        f"type:{m.get('type', '?')}{pp_text})"
                    )
                lines.append(f"  Moves: {', '.join(move_strs)}")
            status = p.get("status", 0)
            if status:
                lines.append(f"  Status: {status}")
            return lines

        lines = [
            f"Battle type: {'Trainer' if is_trainer else 'Wild'}",
            *fmt_pokemon(player_pokemon, "Your Pokemon"),
            *fmt_pokemon(enemy_pokemon, "Enemy"),
        ]
        if weather != "none":
            lines.append(f"Weather: {weather}")

        return "\n".join(lines)

    @staticmethod
    def format_stuck_state(
        location: str,
        stuck_reason: str,
        recent_attempts: list[str],
        position: tuple[int, int],
    ) -> str:
        lines = [
            f"Location: {location} @ ({position[0]},{position[1]})",
            f"Stuck reason: {stuck_reason}",
        ]
        if recent_attempts:
            lines.append("Recent recovery attempts:")
            for attempt in recent_attempts[-5:]:
                lines.append(f"  - {attempt}")
        return "\n".join(lines)
